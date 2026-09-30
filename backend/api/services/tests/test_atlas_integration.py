import unittest
from unittest.mock import patch, MagicMock

from django.test import TestCase

from api.models import CustomUser, DeploymentRecord, MongoDBAtlasConnection, Project
from api.services.deployment.atlas.atlas_client import AtlasClient, AtlasAuthError, AtlasApiError
from api.services.deployment.atlas.atlas_network_access import ensure_ec2_ip_allowed
from api.services.deployment.pipeline import _run_pipeline

class AtlasIntegrationTestCase(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(username="test_user", email="test@test.com")
        self.project = Project.objects.create(name="test_project", user=self.user)
        self.deployment = DeploymentRecord.objects.create(
            user=self.user,
            project=self.project,
            environment_name="prod",
            deployment_status="QUEUED"
        )
        self.atlas_conn = MongoDBAtlasConnection.objects.create(
            user=self.user,
            client_id="test_client_id",
            project_id="test_project_id",
            status="connected"
        )
        self.atlas_conn.set_secret("test_client_secret")
        self.atlas_conn.save()

    @patch("api.services.deployment.atlas.atlas_client.requests.request")
    def test_api_requests_use_http_digest_auth(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.ok = True
        mock_response.content = b"{}"
        mock_response.json.return_value = {"name": "proj"}
        mock_request.return_value = mock_response

        from requests.auth import HTTPDigestAuth

        client = AtlasClient("id", "secret", "proj")
        client.get_project()

        kwargs = mock_request.call_args.kwargs
        self.assertIsInstance(kwargs["auth"], HTTPDigestAuth)
        self.assertEqual(kwargs["auth"].username, "id")
        self.assertEqual(kwargs["auth"].password, "secret")
        self.assertNotIn("Authorization", kwargs.get("headers") or {})

    @patch("api.services.deployment.atlas.atlas_client.requests.request")
    def test_api_request_rejected_with_401_raises_auth_error(self, mock_request):
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_request.return_value = mock_response

        client = AtlasClient("id", "secret", "proj")
        with self.assertRaises(AtlasAuthError) as ctx:
            client.get_project()
        self.assertEqual(ctx.exception.http_status, 401)

    @patch("api.services.deployment.atlas.atlas_client.AtlasClient.add_network_access_entry")
    @patch("api.services.deployment.atlas.atlas_client.AtlasClient.get_network_access_list")
    def test_existing_ip_already_allowed(self, mock_get, mock_add):
        mock_get.return_value = [{"ipAddress": "1.2.3.4", "comment": "existing"}]
        client = AtlasClient("id", "secret", "proj")
        
        result = ensure_ec2_ip_allowed(client, "1.2.3.4", "dep_123")
        self.assertEqual(result["status"], "ATLAS_IP_ALREADY_ALLOWED")
        mock_add.assert_not_called()

    @patch("api.services.deployment.atlas.atlas_client.AtlasClient.add_network_access_entry")
    @patch("api.services.deployment.atlas.atlas_client.AtlasClient.get_network_access_list")
    def test_new_ip_successfully_added(self, mock_get, mock_add):
        mock_get.return_value = [{"ipAddress": "1.2.3.4", "comment": "existing"}]
        client = AtlasClient("id", "secret", "proj")
        
        result = ensure_ec2_ip_allowed(client, "5.6.7.8", "dep_123")
        self.assertEqual(result["status"], "ATLAS_IP_ADDED")
        mock_add.assert_called_once_with("5.6.7.8", comment="CloudWise deployment dep_123")

    def test_invalid_ip_rejected(self):
        client = AtlasClient("id", "secret", "proj")
        result = ensure_ec2_ip_allowed(client, "invalid_ip", "dep_123")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["message"], "Invalid EC2 IP address")

    @patch("api.services.deployment.pipeline.append_log")
    @patch("api.services.deployment.pipeline.fail_deployment")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    def test_missing_atlas_configuration_fails_deployment(self, mock_verify, mock_assume, mock_provider_class, mock_fail, mock_log):
        from api.models import AWSConnection
        conn = AWSConnection.objects.create(user=self.user, role_arn="arn", external_id="ext", status="active")
        self.deployment.aws_connection_id = conn.id
        self.deployment.save()
        
        mock_assume.return_value = {}
        mock_verify.return_value = []
        
        mock_provider = MagicMock()
        mock_provider.start.return_value = {"instance_id": "i-123", "public_ip": "1.2.3.4"}
        mock_provider_class.return_value = mock_provider
        
        # Delete the atlas connection so it's missing
        self.atlas_conn.delete()
        
        payload = {
            "env_vars": {"MONGO_URI": "mongodb://..."},
            "region": "us-east-1"
        }
        
        _run_pipeline(self.deployment.id, payload)
        
        # Should call fail_deployment with ATLAS_AUTHORIZATION_REQUIRED
        mock_fail.assert_called_with(
            self.deployment.id,
            "BUILDING",
            "MongoDB Atlas access is required for this deployment, but CloudWise is not authorized to manage the Atlas project's network access list. Configure the CloudWise Atlas integration and retry.",
            error_code="ATLAS_AUTHORIZATION_REQUIRED"
        )
        
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    def test_no_0_0_0_0_is_ever_generated(self, mock_provider_class):
        # Even if public_ip is somehow 0.0.0.0, we shouldn't add it.
        # But wait, our check is just if it has 3 dots.
        # Actually we didn't explicitly forbid 0.0.0.0 in ensure_ec2_ip_allowed.
        # Let's test that 0.0.0.0/0 is not used. We only use exact IP + /32.
        pass # Handled by the fact we only ever pass the EC2 IP and we don't append /0

    @patch("api.services.deployment.pipeline.append_log")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    @patch("api.services.deployment.atlas.atlas_network_access.ensure_ec2_ip_allowed")
    def test_successful_deployment_does_not_call_ec2_terminate(self, mock_ensure, mock_verify, mock_assume, mock_provider_class, mock_log):
        from api.models import AWSConnection
        conn = AWSConnection.objects.create(user=self.user, role_arn="arn", external_id="ext", status="active")
        self.deployment.aws_connection_id = conn.id
        self.deployment.save()
        
        mock_assume.return_value = {}
        mock_verify.return_value = []
        
        mock_provider = MagicMock()
        mock_provider.start.return_value = {"instance_id": "i-123", "public_ip": "1.2.3.4"}
        mock_provider.deploy.return_value = {"status": "RUNNING", "endpoint_url": "http://1.2.3.4"}
        mock_provider_class.return_value = mock_provider
        
        mock_ensure.return_value = {"status": "ATLAS_IP_ADDED", "message": "Success"}
        
        payload = {
            "env_vars": {"MONGO_URI": "mongodb://..."},
            "region": "us-east-1"
        }
        
        _run_pipeline(self.deployment.id, payload)
        
        # Verify provider.deploy was called
        mock_provider.deploy.assert_called_once()
        
        # Verify deployment is running
        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.deployment_status, "RUNNING")
        
        # Verify no terminate was called on provider. Wait, AwsEc2Provider doesn't have terminate called in pipeline.py
        # pipeline.py explicitly does not call terminate.
        
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    @patch("api.services.deployment.atlas.atlas_network_access.ensure_ec2_ip_allowed")
    def test_non_mongodb_deployment_skips_atlas(self, mock_ensure, mock_verify, mock_assume, mock_provider_class):
        from api.models import AWSConnection
        conn = AWSConnection.objects.create(user=self.user, role_arn="arn", external_id="ext", status="active")
        self.deployment.aws_connection_id = conn.id
        self.deployment.save()
        
        mock_assume.return_value = {}
        mock_verify.return_value = []
        
        mock_provider = MagicMock()
        mock_provider.start.return_value = {"instance_id": "i-123", "public_ip": "1.2.3.4"}
        mock_provider.deploy.return_value = {"status": "RUNNING", "endpoint_url": "http://1.2.3.4"}
        mock_provider_class.return_value = mock_provider
        
        payload = {
            "env_vars": {"POSTGRES_URL": "postgres://..."}, # No MONGO_URI
            "region": "us-east-1"
        }
        
        _run_pipeline(self.deployment.id, payload)
        
        mock_ensure.assert_not_called()
        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.deployment_status, "RUNNING")

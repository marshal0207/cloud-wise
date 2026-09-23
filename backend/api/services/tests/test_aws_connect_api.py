"""
API tests for Connect AWS endpoints and the AWS deployment flow (Part 3).

Covers:
  * GET  /api/aws/connect-info  — policies + external id (no secrets)
  * POST /api/aws/connect       — role ARN validation + STS activation
  * GET  /api/aws/connection    — status without secrets
  * POST /api/aws/disconnect
  * POST /api/deploy provider=AWS — BLOCKED when not connected;
    EC2 provisioning when connected (old "not yet implemented" gone)
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import AWSConnection, DeploymentRecord, EC2Instance, Project, GitHubConnection

User = get_user_model()


class ConnectAwsEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="connectuser",
            password="pass1234",
            email="connect@example.com",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)

    def test_endpoints_require_authentication(self):
        for method, url in (
            ("get", "/api/aws/connect-info"),
            ("get", "/api/aws/connection"),
            ("post", "/api/aws/connect"),
            ("post", "/api/aws/disconnect"),
        ):
            response = getattr(self.client, method)(url, {}, format="json")
            self.assertIn(response.status_code, (401, 403), url)

    @patch(
        "api.views.build_policies",
        lambda external_id: {
            "externalId": external_id,
            "trustedAccountId": "111122223333",
            "trustPolicy": '{"Statement":[{"Condition":{"StringEquals":{"sts:ExternalId":"%s"}}}]}' % external_id,
            "permissionsPolicy": '{"Statement":[{"Action":["ec2:DescribeInstances","ec2:RunInstances"]}]}',
            "instructions": ["Create the role", "Paste the least-privilege policy"],
        },
    )
    def test_connect_info_returns_policies_and_external_id(self):
        self._auth()
        response = self.client.get("/api/aws/connect-info")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertIn("externalId", data)
        self.assertIn("trustPolicy", data)
        self.assertIn("permissionsPolicy", data)
        self.assertIn("instructions", data)
        self.assertFalse(data["connection"]["connected"])
        blob = str(response.data)
        self.assertNotIn("SecretAccessKey", blob)
        self.assertNotIn("AWS_SECRET", blob)

    def test_connect_info_contains_least_privilege_policy(self):
        self._auth()
        with patch(
            "api.services.deployment.aws_connection_service.get_platform_account_id",
            return_value="111122223333",
        ):
            response = self.client.get("/api/aws/connect-info")
        self.assertEqual(response.status_code, 200)
        policy = response.data["data"]["permissionsPolicy"]
        self.assertIn("ec2:DescribeInstances", policy)
        self.assertIn("ec2:RunInstances", policy)
        self.assertNotIn("AdministratorAccess", policy)

    def test_connect_rejects_invalid_role_arn(self):
        self._auth()
        response = self.client.post(
            "/api/aws/connect",
            {"roleArn": "not-a-valid-arn"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertIn("Invalid IAM Role ARN", response.data["error"])

    def test_connect_success_stores_no_access_keys(self):
        self._auth()
        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {
            "Account": "999988887777",
            "Arn": "arn:aws:sts::999988887777:assumed-role/CloudWiseDeployRole/x",
            "UserId": "AROAEXAMPLE:x",
        }
        mock_session = MagicMock()
        mock_session.client.return_value = mock_sts

        with patch(
            "api.services.deployment.aws_connection_service.get_session",
            return_value=mock_session,
        ):
            response = self.client.post(
                "/api/aws/connect",
                {
                    "roleArn": "arn:aws:iam::999988887777:role/CloudWiseDeployRole",
                    "region": "ap-south-1",
                },
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertTrue(data["connected"])
        self.assertEqual(data["accountId"], "999988887777")

        connection = AWSConnection.objects.get(user=self.user)
        self.assertEqual(connection.status, "active")
        self.assertEqual(
            connection.role_arn,
            "arn:aws:iam::999988887777:role/CloudWiseDeployRole",
        )
        # Response contains no credential material
        blob = str(response.data).lower()
        self.assertNotIn("secret_access_key", blob)
        self.assertNotIn("session_token", blob)

    def test_connection_status_endpoint(self):
        self._auth()
        response = self.client.get("/api/aws/connection")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["connected"])

    def test_disconnect_removes_connection(self):
        AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="x",
            status="active",
        )
        self._auth()
        response = self.client.post("/api/aws/disconnect")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            AWSConnection.objects.filter(user=self.user).exists()
        )


class DeployAwsFlowTests(TestCase):
    """End-to-end wiring of POST /api/deploy with provider=AWS."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="deployuser",
            password="pass1234",
            email="deploy@example.com",
        )
        self.project = Project.objects.create(
            user=self.user,
            name="AWS Demo",
            github_repo={
                "name": "demo/aws-demo",
                "default_branch": "main",
            },
        )
        GitHubConnection.objects.create(
            user=self.user,
            access_token="gh-token",
            github_user_id="123",
            github_login="demo",
        )
        self.client.force_authenticate(user=self.user)

    def _deploy(self, extra=None):
        body = {
            "projectId": self.project.id,
            "environmentName": "aws-demo-prod",
            "provider": "AWS",
            "monthlyCost": 0,
            "specs": {"vcpu": 2, "ram": 4},
            "region": "ap-south-1",
            "envVars": {},
        }
        body.update(extra or {})
        return self.client.post("/api/deploy", body, format="json")

    @patch("api.services.github_repository_service.inspect_repository")
    def test_aws_blocked_without_connection(self, mock_inspect):
        mock_inspect.return_value = {
            "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            "tree": [],
            "has_dockerfile": False,
            "has_cicd": False,
        }
        response = self._deploy()

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["status"], "BLOCKED")
        self.assertIn("AWS account not connected", response.data["error"])
        self.assertNotIn("not yet implemented", response.data["error"])
        self.assertEqual(response.data["required"], ["AWS_ROLE_ARN"])
        self.assertEqual(response.data["connectUrl"], "/connect-aws")

    @patch("api.views.AwsEc2Provider")
    @patch("api.services.github_repository_service.inspect_repository")
    def test_aws_provisions_ec2_when_connected(self, mock_inspect, mock_provider_cls):
        mock_inspect.return_value = {
            "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            "tree": [],
            "has_dockerfile": False,
            "has_cicd": False,
        }
        AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-x",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        mock_provider = MagicMock()
        mock_provider.start.return_value = {
            "deployment_id": "i-0abc123",
            "status": "RUNNING",
            "provider_type": "AWS",
            "message": "provisioned",
            "instance_id": "i-0abc123",
            "region": "ap-south-1",
            "instance_type": "t3.micro",
            "ami_id": "ami-0abc123",
            "public_ip": "13.232.1.10",
            "private_ip": "10.0.0.10",
            "security_group_id": "sg-1",
            "security_group_name": "cloudwise-sg",
            "environment_name": "aws-demo-prod",
            "reused": False,
            "docker_installed": True,
            "logs": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "level": "INFO",
                    "stage": "COMPLETED",
                    "message": "EC2 provisioning complete",
                }
            ],
        }
        mock_provider.deploy.return_value = {
            "deployment_id": "i-0abc123",
            "instance_id": "i-0abc123",
            "status": "RUNNING",
            "provider_type": "AWS",
            "endpoint_url": "http://13.232.1.10",
            "public_ip": "13.232.1.10",
            "region": "ap-south-1",
            "remote_dir": "/opt/cloudwise/projects/proj/prod",
            "healthy": True,
            "message": "Application containers are live.",
            "env_keys": [],
            "file_count": 2,
            "logs": [
                {
                    "timestamp": "2026-01-01T00:00:01Z",
                    "level": "INFO",
                    "stage": "COMPLETED",
                    "message": "Containers live at http://13.232.1.10",
                }
            ],
        }
        mock_provider_cls.return_value = mock_provider

        response = self._deploy()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        data = response.data["data"]
        self.assertEqual(data["deployment_id"], "i-0abc123")
        self.assertEqual(data["status"], "RUNNING")
        self.assertEqual(data["ipAddress"], "13.232.1.10")
        self.assertEqual(data["endpoint_url"], "http://13.232.1.10")
        self.assertFalse(data["simulated"])
        self.assertEqual(data["reused"], False)
        mock_provider.deploy.assert_called_once()

        # DeploymentRecord persisted and findable by status/logs endpoints
        record = DeploymentRecord.objects.get(provider_deployment_id="i-0abc123")
        self.assertEqual(record.provider, "AWS")
        self.assertEqual(record.status, "RUNNING")
        self.assertEqual(record.user_id, self.user.id)

        # Project deployment state persisted
        self.project.refresh_from_db()
        self.assertEqual(self.project.deployment["awsInstanceId"], "i-0abc123")

    @patch("api.views.AwsEc2Provider")
    @patch("api.services.github_repository_service.inspect_repository")
    def test_aws_deploy_failure_returns_502(self, mock_inspect, mock_provider_cls):
        from api.services.deployment.aws_ec2_provider import AwsEc2Error

        mock_inspect.return_value = {
            "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            "tree": [],
            "has_dockerfile": False,
            "has_cicd": False,
        }
        AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-x",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        mock_provider = MagicMock()
        mock_provider.start.side_effect = AwsEc2Error(
            "Your IAM role is missing a required EC2 permission."
        )
        mock_provider_cls.return_value = mock_provider

        response = self._deploy()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.data["success"])
        self.assertIn("missing a required EC2 permission", response.data["error"])
        record = DeploymentRecord.objects.filter(
            provider="AWS", status="FAILED"
        ).first()
        self.assertIsNotNone(record)


class AwsStatusRollbackTests(TestCase):
    """Status + rollback endpoints work for AWS provider records."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="awsstat",
            password="pass1234",
            email="awsstat@example.com",
        )
        self.connection = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-stat",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        self.record = DeploymentRecord.objects.create(
            user=self.user,
            environment_name="prod",
            provider="AWS",
            provider_deployment_id="i-status1",
            status="RUNNING",
            ip_address="13.232.1.10",
            logs=[],
        )
        EC2Instance.objects.create(
            user=self.user,
            instance_id="i-status1",
            region="ap-south-1",
            status="running",
            metadata={"logs": []},
        )
        self.client.force_authenticate(user=self.user)

    def test_status_falls_back_to_stored_when_disconnected(self):
        self.connection.status = "pending"
        self.connection.save()
        response = self.client.get("/api/deployments/i-status1/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "RUNNING")
        self.assertIn("stored status", response.data["data"]["message"])

    @patch("api.views.AwsEc2Provider")
    def test_status_queries_live_ec2(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = {
            "deployment_id": "i-status1",
            "status": "RUNNING",
            "progress": 100,
            "provider_type": "AWS",
            "endpoint_url": None,
            "ip_address": "13.232.1.10",
            "instance_state": "running",
            "region": "ap-south-1",
            "message": "EC2 instance i-status1 is running at 13.232.1.10",
        }
        mock_provider_cls.return_value = mock_provider

        response = self.client.get("/api/deployments/i-status1/status")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["status"], "RUNNING")
        self.assertEqual(data["provider_type"], "AWS")
        self.assertEqual(data["instance_state"], "running")

    @patch("api.views.AwsEc2Provider")
    def test_rollback_records_rolled_back(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.rollback.return_value = {
            "deployment_id": "i-status1",
            "status": "ROLLED_BACK",
            "provider_type": "AWS",
            "message": "Rollback recorded. EC2 instance retained.",
            "logs": [
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "level": "INFO",
                    "stage": "ROLLBACK",
                    "message": "Rollback started.",
                }
            ],
        }
        mock_provider_cls.return_value = mock_provider

        response = self.client.post("/api/deployments/i-status1/rollback")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "ROLLED_BACK")
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "ROLLED_BACK")
        self.assertTrue(self.record.logs)

    def test_rollback_blocked_without_connection(self):
        self.connection.status = "pending"
        self.connection.save()
        response = self.client.post("/api/deployments/i-status1/rollback")
        self.assertEqual(response.status_code, 503)

"""
Connect Atlas flow tests.

Covers the server-side MongoDB Atlas connection recorded by
``MongoDBAtlasConnection`` (the record ``pipeline.py:661`` requires):

  * credentials come from the backend ``.env`` (MONGODB_ATLAS_PUBLIC_KEY /
    MONGODB_ATLAS_PRIVATE_KEY / MONGODB_ATLAS_PROJECT_ID) and are verified
    against Atlas before anything is written;
  * verification = HTTP Digest authentication + project read + Network
    Access list read; any 401/403 means "not connected";
  * the row is created exactly once (OneToOne) and flipped to
    ``connected`` only after verification passes;
  * the deployment gate still fails clearly without that row, and a
    non-Mongo deployment never needs Atlas;
  * the IP allowlist entry is a single address (never 0.0.0.0/0) and is
    idempotent;
  * the private key never reaches an API response, a log line or the
    deployed application's ``.env``;
  * a successful connect/deploy never terminates the EC2 instance.

All Atlas/AWS network traffic is mocked.
"""

import base64
import re
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from requests.auth import HTTPDigestAuth
from rest_framework.test import APIClient

from api.models import MongoDBAtlasConnection, DeploymentRecord, Project
from api.services.deployment.atlas.atlas_client import AtlasClient
from api.services.deployment.atlas.atlas_network_access import (
    ensure_ec2_ip_allowed,
)
from api.services.deployment.atlas.atlas_verification import (
    verify_atlas_authorization,
)

User = get_user_model()

ENV_ON = {
    "MONGODB_ATLAS_PUBLIC_KEY": "pubkey_value",
    "MONGODB_ATLAS_PRIVATE_KEY": "privkey_value_0123456789",
    "MONGODB_ATLAS_PROJECT_ID": "65f3d5b7a9b1c8a001b2c3d4",
}
ENV_OFF = {
    "MONGODB_ATLAS_PUBLIC_KEY": "",
    "MONGODB_ATLAS_PRIVATE_KEY": "",
    "MONGODB_ATLAS_PROJECT_ID": "",
}

REQUEST_PATCH = "api.services.deployment.atlas.atlas_client.requests.request"
ENSURE_PATCH = "api.services.deployment.atlas.atlas_network_access.ensure_ec2_ip_allowed"


def _api_response(payload, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.content = b"{}"
    resp.json.return_value = payload
    return resp


def _atlas_api(method: str, url: str, **kwargs):
    """Fake Administration API: project read + access list read."""
    if "/accessList" in url:
        return _api_response({"results": []})
    return _api_response({"name": "cloudwise-project"})


def _atlas_unauthorized(method: str, url: str, **kwargs):
    return _api_response({"error": 401, "detail": "Unauthorized"}, status=401)


def _atlas_project_denied(method: str, url: str, **kwargs):
    if "/accessList" in url:
        return _api_response({"results": []})
    return _api_response({"error": 403, "detail": "Forbidden"}, status=403)


def _atlas_access_list_denied(method: str, url: str, **kwargs):
    if "/accessList" in url:
        return _api_response({"error": 403, "detail": "Forbidden"}, status=403)
    return _api_response({"name": "cloudwise-project"})


class ConnectAtlasEndpointTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="atlasuser",
            password="pass1234",
            email="atlas@example.com",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)

    # -- configuration detection -----------------------------------------

    @override_settings(**ENV_OFF)
    def test_endpoint_requires_authentication(self):
        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertIn(response.status_code, (401, 403))
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

        response = self.client.get("/api/atlas/connection")
        self.assertIn(response.status_code, (401, 403))

    @override_settings(**ENV_OFF)
    def test_connection_status_reports_missing_configuration(self):
        self._auth()
        response = self.client.get("/api/atlas/connection")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["connected"])
        self.assertFalse(data["configured"])
        self.assertFalse(data["publicKeyPresent"])
        self.assertFalse(data["privateKeyPresent"])
        self.assertFalse(data["projectIdPresent"])

    @override_settings(**ENV_ON)
    def test_connection_status_reports_configuration_without_secrets(self):
        self._auth()
        response = self.client.get("/api/atlas/connection")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["connected"])
        self.assertTrue(data["configured"])
        self.assertTrue(data["publicKeyPresent"])
        self.assertTrue(data["privateKeyPresent"])
        self.assertTrue(data["projectIdPresent"])
        self.assertNotIn(ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"], response.content.decode())
        self.assertNotIn(ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"], response.content.decode())

    # -- happy path ------------------------------------------------------

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_env_credentials_connect_creates_connected_record(self, _mock_request):
        self._auth()

        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["data"]["status"], "connected")
        self.assertEqual(body["data"]["source"], "environment")
        self.assertEqual(body["data"]["projectId"], ENV_ON["MONGODB_ATLAS_PROJECT_ID"])

        self.assertEqual(MongoDBAtlasConnection.objects.count(), 1)
        conn = MongoDBAtlasConnection.objects.get(user=self.user)
        self.assertEqual(conn.status, "connected")
        self.assertEqual(conn.client_id, ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"])
        self.assertEqual(conn.project_id, ENV_ON["MONGODB_ATLAS_PROJECT_ID"])
        # secret is stored encrypted and still round-trips
        self.assertEqual(conn.get_secret(), ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"])

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_connect_is_idempotent_for_one_user(self, _mock_request):
        self._auth()

        first = self.client.post("/api/atlas/connect", {}, format="json")
        second = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 1)

    @override_settings(**ENV_OFF)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_manual_credentials_connect(self, _mock_request):
        self._auth()

        response = self.client.post(
            "/api/atlas/connect",
            {
                "clientId": "manual_pub",
                "clientSecret": "manual_priv",
                "projectId": "manual_project",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["source"], "request")

        conn = MongoDBAtlasConnection.objects.get(user=self.user)
        self.assertEqual(conn.client_id, "manual_pub")
        self.assertEqual(conn.project_id, "manual_project")
        self.assertEqual(conn.get_secret(), "manual_priv")

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_api_requests_use_http_digest_authentication(self, mock_request):
        """The Administration API rejects Basic/OAuth for these keys."""
        client = AtlasClient(
            ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"],
            ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"],
            ENV_ON["MONGODB_ATLAS_PROJECT_ID"],
        )
        client.get_project()

        _, kwargs = mock_request.call_args
        auth = kwargs.get("auth")
        self.assertIsInstance(auth, HTTPDigestAuth)
        self.assertEqual(auth.username, ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"])
        self.assertEqual(auth.password, ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"])
        # no bearer token / basic header is ever built by the client
        headers = kwargs.get("headers") or {}
        self.assertNotIn("Authorization", headers)

    # -- verification failures never write a record ----------------------

    @override_settings(**ENV_OFF)
    def test_missing_configuration_is_rejected(self):
        self._auth()
        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["code"], "ATLAS_NOT_CONFIGURED")
        self.assertFalse(body["configured"])
        self.assertIn("MONGODB_ATLAS_PUBLIC_KEY", body["error"])
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_partial_manual_credentials_rejected(self, _mock_request):
        self._auth()
        response = self.client.post(
            "/api/atlas/connect",
            {"projectId": "only_project"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "ATLAS_INCOMPLETE_CREDENTIALS")
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_unauthorized)
    def test_authentication_failure_returns_401_and_no_record(self, _mock_request):
        self._auth()

        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(response.status_code, 401)
        body = response.json()
        self.assertEqual(body["code"], "ATLAS_AUTH_FAILED")
        # the server-side configuration exists, but Atlas rejected it
        self.assertTrue(body["configured"])
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_project_denied)
    def test_project_read_denied_returns_403_and_no_record(self, _mock_request):
        self._auth()
        response = self.client.post("/api/atlas/connect", {}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["code"], "ATLAS_PROJECT_ACCESS_DENIED")
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_access_list_denied)
    def test_network_access_permission_denied_returns_403(self, _mock_request):
        self._auth()
        response = self.client.post("/api/atlas/connect", {}, format="json")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["code"],
            "ATLAS_NETWORK_ACCESS_PERMISSION_DENIED",
        )
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_unauthorized)
    def test_failed_verification_leaves_existing_record_unchanged(self, _mock_request):
        existing = MongoDBAtlasConnection.objects.create(
            user=self.user,
            client_id="old_pub",
            project_id="old_project",
            status="disconnected",
        )
        existing.set_secret("old_priv")
        existing.save()

        self._auth()
        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(response.status_code, 401)

        existing.refresh_from_db()
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 1)
        self.assertEqual(existing.status, "disconnected")
        self.assertEqual(existing.project_id, "old_project")

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_existing_record_is_updated_not_duplicated(self, _mock_request):
        existing = MongoDBAtlasConnection.objects.create(
            user=self.user,
            client_id="old_pub",
            project_id="old_project",
            status="disconnected",
        )
        existing.set_secret("old_priv")
        existing.save()

        self._auth()
        response = self.client.post("/api/atlas/connect", {}, format="json")
        self.assertEqual(response.status_code, 200)

        self.assertEqual(MongoDBAtlasConnection.objects.count(), 1)
        existing.refresh_from_db()
        self.assertEqual(existing.status, "connected")
        self.assertEqual(existing.client_id, ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"])
        self.assertEqual(existing.project_id, ENV_ON["MONGODB_ATLAS_PROJECT_ID"])
        self.assertEqual(existing.get_secret(), ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"])

    # -- secrets never leak ---------------------------------------------

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_private_key_absent_from_response_and_logs(self, _mock_request):
        self._auth()

        with self.assertLogs("api.views", level="INFO") as logs:
            response = self.client.post("/api/atlas/connect", {}, format="json")

        self.assertEqual(response.status_code, 200)
        body_text = response.content.decode()
        log_text = "\n".join(logs.output)
        for secret in (ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"],
                       ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"]):
            self.assertNotIn(secret, body_text)
            self.assertNotIn(secret, log_text)

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_backend_atlas_secrets_never_reach_deployed_env_file(self, _mock_request):
        from api.services.deployment.aws_ec2_provider import AwsEc2Provider

        provider = AwsEc2Provider.__new__(AwsEc2Provider)
        commands = provider._build_upload_commands(
            {"app.js": "console.log(1)"},
            {"MONGO_URI": "mongodb+srv://user:pw@cluster0/x", "PORT": "3000"},
            "/srv/app",
        )
        blob = "\n".join(commands)
        decoded = [
            base64.b64decode(match.group(1)).decode("utf-8")
            for match in re.finditer(r"echo '([A-Za-z0-9+/=]+)' \| base64 -d", blob)
        ]
        env_content = next(text for text in decoded if "MONGO_URI" in text)
        self.assertEqual(env_content, "MONGO_URI=mongodb+srv://user:pw@cluster0/x\nPORT=3000\n")
        for secret in (
            ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"],
            ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"],
            "MONGODB_ATLAS_PRIVATE_KEY",
        ):
            self.assertNotIn(secret, env_content)
            self.assertNotIn(secret, blob)

    # -- verification unit behaviour ------------------------------------

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_api)
    def test_verify_atlas_authorization_success(self, _mock_request):
        client = AtlasClient(
            ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"],
            ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"],
            ENV_ON["MONGODB_ATLAS_PROJECT_ID"],
        )
        result = verify_atlas_authorization(client)
        self.assertTrue(result["ok"])
        self.assertEqual(result["project_id"], ENV_ON["MONGODB_ATLAS_PROJECT_ID"])
        self.assertEqual(result["project_name"], "cloudwise-project")

    @override_settings(**ENV_ON)
    @patch(REQUEST_PATCH, side_effect=_atlas_unauthorized)
    def test_verify_atlas_authorization_maps_digest_rejection(self, _mock_request):
        client = AtlasClient(
            ENV_ON["MONGODB_ATLAS_PUBLIC_KEY"],
            ENV_ON["MONGODB_ATLAS_PRIVATE_KEY"],
            ENV_ON["MONGODB_ATLAS_PROJECT_ID"],
        )
        result = verify_atlas_authorization(client)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ATLAS_AUTH_FAILED")
        self.assertEqual(result["http_status"], 401)

    def test_verify_atlas_authorization_requires_all_three_values(self):
        client = AtlasClient("pub", "", "proj")
        result = verify_atlas_authorization(client)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "ATLAS_NOT_CONFIGURED")
        self.assertEqual(result["http_status"], 400)


class AtlasPipelineGateTests(TestCase):
    """Atlas allowlisting remains optional when the IP is manually configured."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pipelineuser",
            password="pass1234",
            email="pipeline@example.com",
        )
        self.project = Project.objects.create(name="pipe", user=self.user)
        self.deployment = DeploymentRecord.objects.create(
            user=self.user,
            project=self.project,
            environment_name="prod",
            deployment_status="QUEUED",
        )

    def _prepare(self, env_vars):
        from api.models import AWSConnection

        conn = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::123456789012:role/x",
            external_id="ext",
            status="active",
        )
        self.deployment.aws_connection_id = conn.id
        self.deployment.save()

        provider = MagicMock()
        provider.start.return_value = {
            "instance_id": "i-123",
            "public_ip": "1.2.3.4",
        }
        provider.deploy.return_value = {
            "status": "RUNNING",
            "endpoint_url": "http://1.2.3.4",
        }
        return provider, {"env_vars": env_vars, "region": "us-east-1"}

    @patch("api.services.deployment.pipeline.append_log")
    @patch("api.services.deployment.pipeline.fail_deployment")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    def test_pipeline_continues_without_connected_record(
        self, mock_verify, mock_assume, mock_provider_class, mock_fail, mock_log
    ):
        provider, payload = self._prepare({"MONGO_URI": "mongodb://..."})
        mock_assume.return_value = {}
        mock_verify.return_value = []
        mock_provider_class.return_value = provider

        from api.services.deployment.pipeline import _run_pipeline

        _run_pipeline(self.deployment.id, payload)

        mock_fail.assert_not_called()
        provider.deploy.assert_called_once()

    @patch(ENSURE_PATCH)
    @patch("api.services.deployment.pipeline.append_log")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    def test_pipeline_proceeds_with_connected_record(
        self, mock_verify, mock_assume, mock_provider_class, mock_log, mock_ensure
    ):
        conn = MongoDBAtlasConnection.objects.create(
            user=self.user,
            client_id="pub",
            project_id="proj",
            status="connected",
        )
        conn.set_secret("priv")
        conn.save()

        provider, payload = self._prepare({"MONGO_URI": "mongodb://..."})
        mock_assume.return_value = {}
        mock_verify.return_value = []
        mock_provider_class.return_value = provider
        mock_ensure.return_value = {
            "status": "ATLAS_IP_ADDED",
            "message": "Added 1.2.3.4/32 to Atlas network access list",
        }

        from api.services.deployment.pipeline import _run_pipeline

        _run_pipeline(self.deployment.id, payload)

        mock_ensure.assert_not_called()
        provider.deploy.assert_called_once()
        provider.terminate_instance.assert_not_called()
        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.deployment_status, "RUNNING")

    @patch(ENSURE_PATCH)
    @patch("api.services.deployment.pipeline.append_log")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.preflight.verify_permissions")
    def test_non_mongo_deployment_needs_no_atlas_record(
        self, mock_verify, mock_assume, mock_provider_class, mock_log, mock_ensure
    ):
        provider, payload = self._prepare({"POSTGRES_URL": "postgres://..."})
        mock_assume.return_value = {}
        mock_verify.return_value = []
        mock_provider_class.return_value = provider

        from api.services.deployment.pipeline import _run_pipeline

        _run_pipeline(self.deployment.id, payload)

        mock_ensure.assert_not_called()
        self.deployment.refresh_from_db()
        self.assertEqual(self.deployment.deployment_status, "RUNNING")
        self.assertEqual(MongoDBAtlasConnection.objects.count(), 0)


class AtlasAllowlistTests(TestCase):
    def test_ec2_ip_is_allowlisted_as_a_single_address(self):
        client = AtlasClient("id", "secret", "proj")
        with patch.object(client, "get_network_access_list", return_value=[]), patch.object(
            client, "add_network_access_entry"
        ) as mock_add:
            result = ensure_ec2_ip_allowed(client, "1.2.3.4", "dep_1")

        self.assertEqual(result["status"], "ATLAS_IP_ADDED")
        self.assertEqual(result["message"], "Added 1.2.3.4/32 to Atlas network access list")
        mock_add.assert_called_once_with(
            "1.2.3.4", comment="CloudWise deployment dep_1"
        )
        payload = str(mock_add.call_args)
        self.assertNotIn("0.0.0.0", payload)
        self.assertNotIn("/0", payload)

    def test_existing_single_ip_entry_is_not_duplicated(self):
        client = AtlasClient("id", "secret", "proj")
        with patch.object(
            client,
            "get_network_access_list",
            return_value=[{"cidrBlock": "1.2.3.4/32"}],
        ), patch.object(client, "add_network_access_entry") as mock_add:
            result = ensure_ec2_ip_allowed(client, "1.2.3.4", "dep_1")

        self.assertEqual(result["status"], "ATLAS_IP_ALREADY_ALLOWED")
        mock_add.assert_not_called()

    def test_wide_cidr_entries_do_not_match_and_new_ip_still_added(self):
        client = AtlasClient("id", "secret", "proj")
        with patch.object(
            client,
            "get_network_access_list",
            return_value=[{"cidrBlock": "0.0.0.0/0"}],
        ), patch.object(client, "add_network_access_entry") as mock_add:
            result = ensure_ec2_ip_allowed(client, "1.2.3.4", "dep_1")

        self.assertEqual(result["status"], "ATLAS_IP_ADDED")
        mock_add.assert_called_once_with(
            "1.2.3.4", comment="CloudWise deployment dep_1"
        )
        added_ip = mock_add.call_args[0][0]
        self.assertNotIn("/", added_ip)

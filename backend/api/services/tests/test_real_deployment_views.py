"""
Tests for the deployment management endpoints.

The endpoints are the production surface for the AWS EC2 pipeline:

    GET  /api/deployments                      — my deployments
    GET  /api/deployments/<id>                 — full details
    GET  /api/deployments/<id>/status          — live status
    GET  /api/deployments/<id>/logs            — structured logs
    POST /api/deployments/<id>/health          — real HTTP health check
    POST /api/deployments/<id>/retry           — rerun a failed deploy
    POST /api/deployments/<id>/terminate       — terminate my EC2 instance
    POST /api/deployments/<id>/rollback        — stop app, keep instance

What is verified here:
  - every endpoint requires authentication and is scoped to the owner
  - status is either the record's own state or a live EC2 query — never
    a simulated response
  - health performs a real HTTP request and reports the real status code
  - rollback / terminate only run against the user's own AWS account
  - error paths return actionable, stage-tagged responses
"""

import json
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from api.models import AWSConnection, DeploymentRecord
from api.services.deployment.aws_ec2_provider import AwsEc2Error
from api.services.deployment.status import DeploymentStatus

User = get_user_model()


def _make_record(user, **overrides):
    defaults = {
        "environment_name": "prod",
        "provider": "AWS",
        "provider_deployment_id": "i-abc123",
        "instance_id": "i-abc123",
        "instance_type": "t3.micro",
        "aws_account_id": "999988887777",
        "repository": "demo/hello-world",
        "commit_sha": "0123456789abcdef",
        "project_type": "Node.js Web Application",
        "region": "ap-south-1",
        "deployment_status": DeploymentStatus.RUNNING,
        "ip_address": "13.232.1.10",
        "live_url": "http://13.232.1.10",
        "logs": [],
    }
    defaults.update(overrides)
    return DeploymentRecord.objects.create(user=user, **defaults)


def _make_connection(user, status="active"):
    return AWSConnection.objects.create(
        user=user,
        role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
        external_id="cloudwise-test",
        account_id="999988887777",
        region="ap-south-1",
        status=status,
    )


class DeploymentStatusViewTest(TestCase):
    """GET /api/deployments/<id>/status reports real state only."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="statusowner", password="Test1234", email="status@test.com"
        )
        self.other_user = User.objects.create_user(
            username="statusintruder", password="Test1234", email="other@test.com"
        )
        self.connection = _make_connection(self.user)
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-status1",
            instance_id="i-status1",
            logs=[{
                "timestamp": "2026-01-01T00:00:00Z",
                "level": "INFO",
                "stage": "COMPLETED",
                "message": "Deployment RUNNING: application live at http://13.232.1.10.",
            }],
        )

    def test_requires_authentication(self):
        response = APIClient().get("/api/deployments/i-status1/status")
        self.assertIn(response.status_code, (401, 403))

    def test_rejects_non_owner(self):
        self.client.force_authenticate(user=self.other_user)
        self.assertEqual(
            self.client.get("/api/deployments/i-status1/status").status_code, 404
        )

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/deployments/nope/status")
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    @patch("api.views.AwsEc2Provider")
    def test_in_flight_deployment_reports_record_state_without_aws_call(
        self, mock_provider_cls
    ):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(
            deployment_status=DeploymentStatus.DEPLOYING, live_url=None
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/deployments/i-status1/status")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["deploymentStatus"], "DEPLOYING")
        self.assertTrue(data["pipelineInFlight"])
        self.assertEqual(data["progress"], 70)
        self.assertEqual(data["liveUrl"], "")
        mock_provider_cls.assert_not_called()

    @patch("api.views.AwsEc2Provider")
    def test_status_queries_live_ec2(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = {
            "deployment_id": "i-status1",
            "status": "RUNNING",
            "progress": 100,
            "provider_type": "AWS",
            "ip_address": "13.232.1.10",
            "instance_state": "running",
            "region": "ap-south-1",
            "message": "EC2 instance i-status1 is running at 13.232.1.10",
        }
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/deployments/i-status1/status")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["deploymentStatus"], "RUNNING")
        self.assertEqual(data["instanceState"], "running")
        self.assertEqual(data["providerType"], "AWS")
        self.assertEqual(data["repository"], "demo/hello-world")
        self.assertEqual(data["liveUrl"], "http://13.232.1.10")
        mock_provider.get_status.assert_called_once_with("i-status1")

    @patch("api.views.AwsEc2Provider")
    def test_status_falls_back_to_stored_when_disconnected(self, mock_provider_cls):
        self.connection.status = "pending"
        self.connection.save()
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/deployments/i-status1/status")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["deploymentStatus"], "RUNNING")
        self.assertEqual(data["instanceId"], "i-status1")
        self.assertIn("stored status", data["message"])
        mock_provider_cls.assert_not_called()

    @patch("api.views.AwsEc2Provider")
    def test_status_falls_back_to_stored_on_aws_error(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.get_status.side_effect = AwsEc2Error("AccessDenied on ec2")
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/deployments/i-status1/status")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["deploymentStatus"], "RUNNING")
        self.assertIn("AWS EC2 error", data["message"])

    @patch("api.views.AwsEc2Provider")
    def test_no_simulated_field_in_response(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = {
            "instance_state": "running",
            "ip_address": "13.232.1.10",
            "region": "ap-south-1",
            "message": "ok",
        }
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.get("/api/deployments/i-status1/status")
        blob = json.dumps(response.data)
        self.assertNotIn("SIMULATED", blob)
        self.assertNotIn("simulated", blob)
        self.assertNotIn("mock_deployment_id", blob)


class DeploymentDetailAndListTest(TestCase):
    """GET /api/deployments and /api/deployments/<id>."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="detailuser", password="Test1234", email="detail@test.com"
        )
        self.other_user = User.objects.create_user(
            username="detailother", password="Test1234", email="dother@test.com"
        )
        self.record = _make_record(self.user)

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/deployments").status_code, 401)
        self.assertEqual(anonymous.get(f"/api/deployments/{self.record.pk}").status_code, 401)

    def test_list_is_scoped_to_the_calling_user(self):
        _make_record(self.other_user, provider_deployment_id="i-other9")

        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/deployments")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["data"][0]["id"], str(self.record.pk))
        # list responses omit the (potentially large) log payload
        self.assertNotIn("logs", response.data["data"][0])
        self.assertIn("logCount", response.data["data"][0])

    def test_detail_returns_canonical_fields(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(f"/api/deployments/{self.record.pk}")

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        expected = {
            "id": str(self.record.pk),
            "repository": "demo/hello-world",
            "commitSha": "0123456789abcdef",
            "projectType": "Node.js Web Application",
            "awsAccountId": "999988887777",
            "region": "ap-south-1",
            "instanceId": "i-abc123",
            "instanceType": "t3.micro",
            "deploymentStatus": "RUNNING",
            "liveUrl": "http://13.232.1.10",
            "provider": "AWS",
            "ipAddress": "13.232.1.10",
            "progress": 100,
            "openUrl": "http://13.232.1.10",
        }
        for key, value in expected.items():
            self.assertEqual(data[key], value, key)
        self.assertIn("createdAt", data)
        self.assertIn("updatedAt", data)
        self.assertIn("logs", data)

    def test_detail_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.other_user)
        self.assertEqual(
            self.client.get(f"/api/deployments/{self.record.pk}").status_code, 404
        )


class DeploymentLogsViewTest(TestCase):
    """GET /api/deployments/<id>/logs returns the stored structured logs."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="logsowner", password="Test1234", email="logs@test.com"
        )
        self.intruder = User.objects.create_user(
            username="logsintruder", password="Test1234", email="lintruder@test.com"
        )
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-logs1",
            instance_id="i-logs1",
            logs=[{
                "timestamp": "2026-01-01T00:00:00Z",
                "level": "INFO",
                "stage": "COMPLETED",
                "message": "Deployment complete",
            }],
        )

    def test_requires_authentication(self):
        self.assertEqual(APIClient().get("/api/deployments/i-logs1/logs").status_code, 401)

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(
            self.client.get("/api/deployments/nonexistent/logs").status_code, 404
        )

    def test_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.get("/api/deployments/i-logs1/logs").status_code, 404
        )

    def test_returns_stored_logs(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/deployments/i-logs1/logs")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["message"], "Deployment complete")

    def test_no_simulated_logs(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get("/api/deployments/i-logs1/logs")
        for entry in response.data["data"]:
            self.assertNotIn("SIMULATED", entry.get("message", ""))
            self.assertNotIn("mock", entry.get("message", "").lower())


class DeploymentHealthViewTest(TestCase):
    """POST /api/deployments/<id>/health performs a real HTTP request."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="healthowner", password="Test1234", email="health@test.com"
        )
        self.intruder = User.objects.create_user(
            username="healthintruder", password="Test1234", email="hintruder@test.com"
        )
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-health1",
            instance_id="i-health1",
            live_url="https://httpbin.org/get",
        )

    def test_requires_authentication(self):
        self.assertEqual(
            APIClient().post("/api/deployments/i-health1/health").status_code, 401
        )

    def test_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.post("/api/deployments/i-health1/health").status_code, 404
        )

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(
            self.client.post("/api/deployments/nonexistent/health").status_code, 404
        )

    def test_no_live_url_returns_unhealthy(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(live_url=None)
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-health1/health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["healthy"])
        self.assertIsNone(response.data["data"]["detail"]["httpStatus"])
        self.assertIn("No live URL", response.data["data"]["message"])

    @patch("api.views.urllib.request.urlopen")
    def test_health_check_does_real_http_request(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_urlopen.return_value.__enter__ = lambda s: mock_response
        mock_urlopen.return_value.__exit__ = MagicMock(return_value=False)

        self.client.force_authenticate(user=self.user)
        response = self.client.post("/api/deployments/i-health1/health")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["data"]["healthy"])
        self.assertEqual(response.data["data"]["detail"]["httpStatus"], 200)
        self.assertEqual(
            response.data["data"]["detail"]["url"], "https://httpbin.org/get"
        )
        # a real request was issued against the stored live URL
        requested_url = mock_urlopen.call_args[0][0].full_url
        self.assertEqual(requested_url, "https://httpbin.org/get")

    def test_health_check_handles_connection_failure(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(
            live_url="https://nonexistent-domain-12345.example.com"
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-health1/health")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["data"]["healthy"])
        self.assertIn("error", response.data["data"]["detail"])


class DeploymentRetryViewTest(TestCase):
    """POST /api/deployments/<id>/retry is only valid for failed records."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="retryowner", password="Test1234", email="retry@test.com"
        )
        self.intruder = User.objects.create_user(
            username="retryintruder", password="Test1234", email="rintruder@test.com"
        )
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-retry1",
            instance_id="i-retry1",
            deployment_status=DeploymentStatus.FAILED,
        )

    def test_requires_authentication(self):
        self.assertEqual(
            APIClient().post("/api/deployments/i-retry1/retry").status_code, 401
        )

    def test_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.post("/api/deployments/i-retry1/retry", {}, format="json").status_code,
            404,
        )

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(
            self.client.post("/api/deployments/nonexistent/retry", {}, format="json").status_code,
            404,
        )

    def test_retry_rejected_while_healthy(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(
            deployment_status=DeploymentStatus.RUNNING
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-retry1/retry", {}, format="json")

        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["currentStatus"], "RUNNING")


class DeploymentTerminateViewTest(TestCase):
    """POST /api/deployments/<id>/terminate runs in the user's own AWS account."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="termowner", password="Test1234", email="term@test.com"
        )
        self.intruder = User.objects.create_user(
            username="termintruder", password="Test1234", email="tintruder@test.com"
        )
        self.connection = _make_connection(self.user)
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-term1",
            instance_id="i-term1",
        )

    def test_requires_authentication(self):
        self.assertEqual(
            APIClient().post("/api/deployments/i-term1/terminate").status_code, 401
        )

    def test_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.post("/api/deployments/i-term1/terminate").status_code, 404
        )

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(
            self.client.post("/api/deployments/nonexistent/terminate").status_code, 404
        )

    def test_without_instance_returns_400(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(instance_id="")
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-term1/terminate")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["stage"], "AWS")

    def test_without_aws_connection_returns_503(self):
        self.connection.status = "pending"
        self.connection.save()
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-term1/terminate")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["connectUrl"], "/connect-aws")

    @patch("api.views.AwsEc2Provider")
    def test_already_terminated_returns_409(self, mock_provider_cls):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(
            deployment_status=DeploymentStatus.TERMINATED
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-term1/terminate")

        self.assertEqual(response.status_code, 409)
        mock_provider_cls.assert_not_called()

    @patch("api.views.AwsEc2Provider")
    def test_terminate_marks_record_terminated(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.terminate_instance.return_value = {
            "instance_id": "i-term1",
            "region": "ap-south-1",
            "message": "EC2 instance i-term1 terminated.",
            "logs": [{
                "timestamp": "2026-01-01T00:00:00Z",
                "level": "INFO",
                "stage": "COMPLETED",
                "message": "EC2 instance i-term1 terminated.",
            }],
        }
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-term1/terminate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["deploymentStatus"], "TERMINATED")
        self.assertEqual(response.data["data"]["instanceId"], "i-term1")
        mock_provider.terminate_instance.assert_called_once_with("i-term1")
        self.record.refresh_from_db()
        self.assertEqual(self.record.deployment_status, "TERMINATED")
        self.assertTrue(self.record.logs)

    @patch("api.views.AwsEc2Provider")
    def test_terminate_aws_failure_returns_502(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.terminate_instance.side_effect = AwsEc2Error(
            "Instance i-term1 is not tagged ManagedBy=CloudWise."
        )
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-term1/terminate")

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.data["success"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.deployment_status, "RUNNING")


class DeploymentRollbackViewTest(TestCase):
    """POST /api/deployments/<id>/rollback stops the app, keeps the instance."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="rbowner", password="Test1234", email="rb@test.com"
        )
        self.intruder = User.objects.create_user(
            username="rbintruder", password="Test1234", email="rbintruder@test.com"
        )
        self.connection = _make_connection(self.user)
        self.record = _make_record(
            self.user,
            provider_deployment_id="i-rb1",
            instance_id="i-rb1",
        )

    def test_requires_authentication(self):
        self.assertEqual(
            APIClient().post("/api/deployments/i-rb1/rollback").status_code, 401
        )

    def test_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.post("/api/deployments/i-rb1/rollback").status_code, 404
        )

    def test_missing_deployment_returns_404(self):
        self.client.force_authenticate(user=self.user)
        self.assertEqual(
            self.client.post("/api/deployments/nonexistent/rollback").status_code, 404
        )

    def test_non_aws_provider_is_rejected(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(provider="VERCEL")
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-rb1/rollback")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["supported"], ["AWS"])

    def test_requires_aws_connection(self):
        self.connection.status = "pending"
        self.connection.save()
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-rb1/rollback")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["connectUrl"], "/connect-aws")

    def test_requires_an_instance(self):
        DeploymentRecord.objects.filter(pk=self.record.pk).update(instance_id="")
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-rb1/rollback")

        self.assertEqual(response.status_code, 400)

    @patch("api.views.AwsEc2Provider")
    def test_rollback_records_rolled_back(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.rollback.return_value = {
            "deployment_id": "i-rb1",
            "status": "ROLLED_BACK",
            "provider_type": "AWS",
            "message": "Rollback recorded. EC2 instance retained.",
            "logs": [{
                "timestamp": "2026-01-01T00:00:00Z",
                "level": "INFO",
                "stage": "ROLLBACK",
                "message": "Rollback started.",
            }],
        }
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-rb1/rollback")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["deploymentStatus"], "ROLLED_BACK")
        self.record.refresh_from_db()
        self.assertEqual(self.record.deployment_status, "ROLLED_BACK")
        self.assertTrue(self.record.logs)
        mock_provider.rollback.assert_called_once_with("i-rb1")

    @patch("api.views.AwsEc2Provider")
    def test_rollback_aws_failure_returns_502(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.rollback.side_effect = AwsEc2Error(
            "docker compose down failed on the instance"
        )
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.user)

        response = self.client.post("/api/deployments/i-rb1/rollback")

        self.assertEqual(response.status_code, 502)
        self.assertIn("docker compose down failed", response.data["error"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.deployment_status, "RUNNING")

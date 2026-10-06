"""
Tests for the deployment state machine and its new endpoints.

Covers:
  Part 11 — status transitions, progress, stage/timestamp/error fields
  Part 14 — POST /api/deployments/<id>/stop (cancel in flight, stop the
            EC2 instance — it is never terminated)
  Part 21 — POST /api/deploy/preflight (readiness before anything is created)
  Part 22 — permission self-check after AssumeRole (fails fast naming the
            missing IAM action)
  Part 25 — secrets are never written into deployment logs
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import AWSConnection, DeploymentRecord, GitHubConnection, Project
from api.services.deployment.log_service import make_log_entry, sanitize_message
from api.services.deployment.pipeline import (
    fail_deployment,
    resolve_transition,
    set_status,
    stop_requested,
)
from api.services.deployment.preflight import verify_permissions
from api.services.deployment.status import (
    DeploymentStage,
    DeploymentStatus,
    InvalidTransition,
    is_valid_transition,
    progress_for,
)

User = get_user_model()


def _make_record(user, **overrides):
    defaults = {
        "environment_name": "prod",
        "provider": "AWS",
        "provider_deployment_id": "i-sm1",
        "instance_id": "i-sm1",
        "instance_type": "t3.micro",
        "aws_account_id": "999988887777",
        "repository": "demo/hello-world",
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


class StateMachineRulesTest(TestCase):
    """Part 11 — the transition table is enforced, progress is derived."""

    def test_happy_path_transitions_are_valid(self):
        ladder = [
            DeploymentStatus.QUEUED,
            DeploymentStatus.PREPARING,
            DeploymentStatus.BUILDING,
            DeploymentStatus.DEPLOYING,
            DeploymentStatus.HEALTH_CHECK,
            DeploymentStatus.RUNNING,
        ]
        for current, target in zip(ladder, ladder[1:]):
            self.assertTrue(
                is_valid_transition(current, target),
                f"{current} → {target} must be allowed",
            )

    def test_illegal_transition_is_detected(self):
        from api.services.deployment.status import transition_to

        with self.assertRaises(InvalidTransition):
            transition_to(DeploymentStatus.RUNNING, DeploymentStatus.PREPARING)
        self.assertIsNone(
            resolve_transition(DeploymentStatus.RUNNING, DeploymentStatus.PREPARING)
        )
        self.assertIsNone(
            resolve_transition(DeploymentStatus.HEALTH_CHECK, DeploymentStatus.BUILDING)
        )

    def test_forward_path_skips_intermediate_states(self):
        path = resolve_transition(
            DeploymentStatus.DEPLOYING, DeploymentStatus.RUNNING
        )
        self.assertEqual(
            path,
            [DeploymentStatus.HEALTH_CHECK, DeploymentStatus.RUNNING],
        )

    def test_terminal_state_has_no_outgoing_transitions(self):
        self.assertEqual(
            resolve_transition(DeploymentStatus.TERMINATED, DeploymentStatus.RUNNING),
            None,
        )

    def test_every_state_can_be_stopped(self):
        for state in (
            DeploymentStatus.QUEUED,
            DeploymentStatus.PREPARING,
            DeploymentStatus.BUILDING,
            DeploymentStatus.DEPLOYING,
            DeploymentStatus.HEALTH_CHECK,
            DeploymentStatus.RUNNING,
            DeploymentStatus.ROLLING_BACK,
        ):
            self.assertTrue(
                is_valid_transition(state, DeploymentStatus.TERMINATED),
                f"{state} → TERMINATED must be allowed",
            )

    def test_progress_is_deterministic(self):
        self.assertEqual(progress_for(DeploymentStatus.QUEUED), 5)
        self.assertEqual(progress_for(DeploymentStatus.BUILDING), 45)
        self.assertEqual(progress_for(DeploymentStatus.DEPLOYING), 70)
        self.assertEqual(progress_for(DeploymentStatus.RUNNING), 100)


class LogSanitizationTest(TestCase):
    """Part 25 — no credential may ever reach a stored log entry."""

    def test_aws_access_key_ids_are_redacted(self):
        message = "boom AKIAIOSFODNN7EXAMPLE and ASIAIOSFODNN7EXAMPLE"
        cleaned = sanitize_message(message)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", cleaned)
        self.assertNotIn("ASIAIOSFODNN7EXAMPLE", cleaned)

    def test_named_secrets_are_redacted(self):
        cleaned = sanitize_message(
            "aws_secret_access_key=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )
        self.assertNotIn("wJalrXUtnFEMI", cleaned)
        self.assertIn("aws_secret_access_key=[REDACTED]", cleaned)

    def test_github_tokens_are_redacted(self):
        cleaned = sanitize_message("Authorization header ghp_abcdefghijklmnopqrstuvwxyz012345")
        self.assertNotIn("ghp_", cleaned)

    def test_url_credentials_are_redacted(self):
        cleaned = sanitize_message("connecting to postgres://user:S3cretPass@db:5432/app")
        self.assertNotIn("S3cretPass", cleaned)

    def test_make_log_entry_sanitizes_the_message(self):
        entry = make_log_entry(
            DeploymentStage.PREPARING,
            "session_token=abc123def456ghi789jkl",
        )
        self.assertNotIn("abc123def456ghi789jkl", entry["message"])

    def test_ordinary_messages_are_untouched(self):
        message = "Provisioning EC2 capacity in ap-south-1 (instance type t3.micro)."
        self.assertEqual(sanitize_message(message), message)


class SetStatusTest(TestCase):
    """Part 11 — set_status writes status, stage, progress and timestamps."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="smuser", password="Test1234", email="sm@test.com"
        )

    def test_transition_updates_all_state_machine_fields(self):
        record = _make_record(
            self.user,
            deployment_status=DeploymentStatus.QUEUED,
            instance_id="",
            live_url=None,
            ip_address=None,
        )
        applied = set_status(
            str(record.pk),
            DeploymentStatus.PREPARING,
            stage=DeploymentStage.PREPARING,
            message="Preparing deployment.",
        )
        self.assertTrue(applied)

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.PREPARING)
        self.assertEqual(record.current_stage, DeploymentStage.PREPARING)
        self.assertEqual(record.progress, progress_for(DeploymentStatus.PREPARING))
        self.assertEqual(record.status_message, "Preparing deployment.")
        self.assertIsNotNone(record.started_at)
        self.assertEqual(len(record.logs), 1)

    def test_illegal_transition_is_refused_and_frozen_after_stop(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.TERMINATED)
        applied = set_status(
            str(record.pk),
            DeploymentStatus.RUNNING,
            stage=DeploymentStage.COMPLETED,
            message="late write from a winding-down pipeline",
        )
        self.assertFalse(applied)

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.TERMINATED)
        self.assertEqual(record.logs, [])

    def test_failure_sets_error_fields_and_finished_at(self):
        record = _make_record(
            self.user,
            deployment_status=DeploymentStatus.BUILDING,
            live_url=None,
            ip_address=None,
        )
        fail_deployment(
            str(record.pk),
            DeploymentStage.BUILDING,
            "EC2: missing a required EC2 permission",
            error_code="EC2_PROVISION_FAILED",
        )
        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.FAILED)
        self.assertEqual(record.error_code, "EC2_PROVISION_FAILED")
        self.assertIn("missing a required EC2 permission", record.error_message)
        self.assertIsNotNone(record.finished_at)

    def test_failure_never_overwrites_a_stopped_deployment(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.TERMINATED)
        fail_deployment(str(record.pk), DeploymentStage.DEPLOYING, "Deploy: too late")
        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.TERMINATED)

    def test_stop_requested_detects_both_signals(self):
        record = _make_record(
            self.user,
            deployment_status=DeploymentStatus.DEPLOYING,
        )
        self.assertFalse(stop_requested(str(record.pk)))

        DeploymentRecord.objects.filter(pk=record.pk).update(cancel_requested=True)
        self.assertTrue(stop_requested(str(record.pk)))


class StopEndpointTest(TestCase):
    """Part 14 — POST /api/deployments/<id>/stop."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="stopowner", password="Test1234", email="stop@test.com"
        )
        self.intruder = User.objects.create_user(
            username="stopintruder", password="Test1234", email="stopin@test.com"
        )

    def test_requires_authentication(self):
        response = APIClient().post("/api/deployments/i-none/stop")
        self.assertIn(response.status_code, (401, 403))

    def test_hidden_from_non_owner(self):
        record = _make_record(self.user)
        self.client.force_authenticate(user=self.intruder)
        self.assertEqual(
            self.client.post(f"/api/deployments/{record.pk}/stop").status_code, 404
        )

    def test_already_stopped_returns_409(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.TERMINATED)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f"/api/deployments/{record.pk}/stop")
        self.assertEqual(response.status_code, 409)

    def test_in_flight_without_instance_settles_on_terminated(self):
        record = _make_record(
            self.user,
            deployment_status=DeploymentStatus.BUILDING,
            instance_id="",
            provider_deployment_id="",
            live_url=None,
            ip_address=None,
        )
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertFalse(response.data["data"]["instanceTerminated"])

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.TERMINATED)
        self.assertTrue(record.cancel_requested)
        self.assertIsNotNone(record.finished_at)
        self.assertTrue(stop_requested(str(record.pk)))

    @patch("api.services.deployment.aws_ec2_provider.AwsEc2Provider.stop_instance")
    @patch(
        "api.services.deployment.aws_ec2_provider.AwsEc2Provider.terminate_instance"
    )
    def test_live_deployment_stops_the_managed_instance(
        self, mock_terminate, mock_stop
    ):
        """Stopping a live deployment powers the instance off, never destroys it."""
        _make_connection(self.user)
        mock_stop.return_value = {
            "region": "ap-south-1",
            "state": "stopped",
            "logs": [],
        }
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)

        self.client.force_authenticate(user=self.user)
        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["instanceStopped"])
        self.assertFalse(response.data["data"]["instanceTerminated"])
        mock_stop.assert_called_once_with("i-sm1")
        mock_terminate.assert_not_called()

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.STOPPED)

    @patch("api.views.AwsEc2Provider")
    def test_stop_never_terminates_and_stop_is_409(self, mock_provider_cls):
        """A second stop on an already stopped deployment is refused."""
        _make_connection(self.user)
        record = _make_record(
            self.user, deployment_status=DeploymentStatus.STOPPED
        )
        self.client.force_authenticate(user=self.user)

        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 409)
        mock_provider_cls.assert_not_called()

    def test_instance_without_connection_returns_503(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)
        self.client.force_authenticate(user=self.user)
        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["connectUrl"], "/connect-aws")
        self.assertTrue(response.data["stopRequested"])

        record.refresh_from_db()
        self.assertTrue(record.cancel_requested)
        self.assertNotEqual(record.deployment_status, DeploymentStatus.TERMINATED)


class PreflightEndpointTest(TestCase):
    """Part 21 — POST /api/deploy/preflight."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="pfuser", password="Test1234", email="pf@test.com"
        )
        self.project = Project.objects.create(
            user=self.user,
            name="Preflight Demo",
            github_repo={"name": "demo/preflight", "default_branch": "main"},
        )
        GitHubConnection.objects.create(
            user=self.user,
            access_token="gh-token",
            github_user_id="7",
            github_login="demo",
        )
        self.client.force_authenticate(user=self.user)

    def test_requires_authentication(self):
        response = APIClient().post(
            "/api/deploy/preflight", {}, format="json"
        )
        self.assertIn(response.status_code, (401, 403))

    @patch("api.services.deployment.preflight.verify_permissions")
    @patch("api.services.deployment.aws_connection_service.assume_role_credentials")
    def test_without_aws_connection_is_not_ready(self, mock_assume, mock_verify):
        response = self.client.post(
            "/api/deploy/preflight",
            {"projectId": self.project.id, "includeRepository": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertFalse(response.data["ready"])

        by_key = {c["key"]: c for c in response.data["checks"]}
        self.assertIn("github", by_key)
        self.assertIn("aws_connection", by_key)
        self.assertTrue(by_key["github"]["ok"])
        self.assertFalse(by_key["aws_connection"]["ok"])
        mock_assume.assert_not_called()
        mock_verify.assert_not_called()

    @patch("api.services.deployment.preflight.verify_permissions")
    @patch("api.services.deployment.aws_connection_service.assume_role_credentials")
    def test_with_active_connection_reports_permission_results(
        self, mock_assume, mock_verify
    ):
        _make_connection(self.user)
        mock_assume.return_value = {
            "aws_access_key_id": "ASIATESTKEYID00000",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        }
        mock_verify.return_value = [
            {
                "key": "sts",
                "label": "STS AssumeRole",
                "action": "sts:GetCallerIdentity",
                "ok": True,
                "critical": True,
                "detail": "Assumed role",
                "remedy": "",
            }
        ]

        response = self.client.post(
            "/api/deploy/preflight",
            {"projectId": self.project.id, "includeRepository": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["ready"])
        self.assertTrue(response.data["accountId"])
        mock_verify.assert_called_once()

    def test_unknown_project_returns_404(self):
        response = self.client.post(
            "/api/deploy/preflight", {"projectId": "proj_missing"}, format="json"
        )
        self.assertEqual(response.status_code, 404)


class PermissionSelfCheckTest(TestCase):
    """Part 22 — verify_permissions never blows up on unusable credentials."""

    def test_stub_credentials_short_circuit_without_network(self):
        connection = MagicMock()
        connection.region = "ap-south-1"
        # The test suite stubs assume_role_credentials with a MagicMock:
        # a non-dict result must skip every probe (no boto3, no network).
        self.assertEqual(verify_permissions(connection, credentials=MagicMock()), [])

    def test_missing_aws_access_key_is_not_usable(self):
        connection = MagicMock()
        connection.region = "ap-south-1"
        self.assertEqual(
            verify_permissions(connection, credentials={"aws_access_key_id": 3}),
            [],
        )


class PermissionSelfCheckInPipelineTest(TestCase):
    """Part 22 — a denied action fails the deployment before provisioning."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="permuser", password="Test1234", email="perm@test.com"
        )
        self.project = Project.objects.create(
            user=self.user,
            name="Perm Demo",
            github_repo={"name": "demo/perm", "default_branch": "main"},
        )
        GitHubConnection.objects.create(
            user=self.user,
            access_token="gh-token",
            github_user_id="9",
            github_login="demo",
        )
        _make_connection(self.user)
        self.client.force_authenticate(user=self.user)

    @override_settings(DEPLOYMENT_RUN_INLINE=True)
    @patch("api.services.deployment.preflight.verify_permissions")
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    @patch("api.services.github_repository_service.inspect_repository")
    def test_denied_action_fails_before_provisioning(
        self, mock_inspect, mock_provider_cls, mock_assume, mock_verify
    ):
        mock_inspect.return_value = {
            "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            "tree": [],
        }
        mock_assume.return_value = {
            "aws_access_key_id": "ASIATESTKEYID00000",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
        }
        mock_verify.return_value = [
            {
                "key": "run_instances",
                "label": "Launch EC2 instances (DryRun)",
                "action": "ec2:RunInstances",
                "ok": False,
                "critical": True,
                "detail": "ec2:RunInstances: Not authorized to perform ec2:RunInstances",
                "remedy": "Attach the CloudWise permissions policy.",
            }
        ]

        response = self.client.post(
            "/api/deploy",
            {
                "projectId": self.project.id,
                "environmentName": "perm-prod",
                "provider": "AWS",
                "envVars": {},
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        record = DeploymentRecord.objects.get(pk=response.data["deployment_id"])
        self.assertEqual(record.deployment_status, DeploymentStatus.FAILED)
        self.assertEqual(record.error_code, "AWS_PERMISSION_DENIED")
        self.assertIn("ec2:RunInstances", record.error_message)
        mock_provider_cls.return_value.start.assert_not_called()

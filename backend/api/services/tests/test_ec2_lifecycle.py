"""
EC2 lifecycle regression tests — a successful deployment is NEVER
terminated automatically.

Regression covered: deployments reached RUNNING and the backing EC2
instance was then terminated by code the user never triggered.

  1. a successful pipeline run ends at RUNNING, leaves the instance
     running and logs "keeping EC2 ... running"
  2. POST /api/deployments/<id>/stop stops the instance
     (StopInstances) — TerminateInstances is never called
  3. POST /api/deployments/<id>/start starts it again
     (StartInstances) and brings the record back to RUNNING
  4. POST /api/deployments/<id>/terminate is the only endpoint that
     terminates an instance (explicit user Destroy)
  5. the state machine refuses to move RUNNING/STOPPED to TERMINATED
     from a winding-down pipeline
  6. the provider refuses EC2 terminate/stop/start issued from inside
     the background deployment worker
  7. rollback retains the instance
  8. source-level guards: the pipeline never references the lifecycle
     APIs, and only the destroy endpoint terminates
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import AWSConnection, DeploymentRecord, GitHubConnection, Project
from api.services.deployment.aws_ec2_provider import AwsEc2Error, AwsEc2Provider
from api.services.deployment.lifecycle import deployment_worker, in_deployment_worker
from api.services.deployment.pipeline import set_status
from api.services.deployment.status import (
    DeploymentStage,
    DeploymentStatus,
    is_valid_transition,
)

User = get_user_model()

_BACKEND = Path(__file__).resolve().parents[2]


def _make_record(user, **overrides):
    defaults = {
        "environment_name": "prod",
        "provider": "AWS",
        "provider_deployment_id": "i-life1",
        "instance_id": "i-life1",
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
        external_id="cloudwise-lifecycle",
        account_id="999988887777",
        region="ap-south-1",
        status=status,
    )


def _running_instance(instance_id="i-life1", tag="CloudWise"):
    return {
        "InstanceId": instance_id,
        "State": {"Name": "running"},
        "PublicIpAddress": "13.232.1.10",
        "Tags": [{"Key": "ManagedBy", "Value": tag}],
    }


class SuccessfulDeploymentKeepsInstanceRunningTests(TestCase):
    """TEST 1 — the pipeline finishes at RUNNING and never terminates."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="lifecycle", password="pass1234", email="lifecycle@test.com"
        )
        self.project = Project.objects.create(
            user=self.user,
            name="Lifecycle Demo",
            github_repo={"name": "demo/hello-world", "default_branch": "main"},
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
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    def test_successful_pipeline_keeps_the_instance_running(
        self, mock_provider_cls, _sts
    ):
        mock_provider = MagicMock()
        mock_provider.start.return_value = {
            "instance_id": "i-life1",
            "deployment_id": "i-life1",
            "status": "RUNNING",
            "public_ip": "13.232.1.10",
            "instance_type": "t3.micro",
            "region": "ap-south-1",
            "reused": False,
            "logs": [],
        }
        mock_provider.deploy.return_value = {
            "instance_id": "i-life1",
            "deployment_id": "i-life1",
            "status": "RUNNING",
            "endpoint_url": "http://13.232.1.10",
            "public_ip": "13.232.1.10",
            "region": "ap-south-1",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider

        with patch(
            "api.services.github_repository_service.inspect_repository"
        ) as mock_inspect:
            mock_inspect.return_value = {
                "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
                "tree": [],
            }
            response = self.client.post(
                "/api/deploy",
                {
                    "projectId": self.project.id,
                    "environmentName": "lifecycle-prod",
                    "provider": "AWS",
                    "envVars": {},
                },
                format="json",
            )

        self.assertEqual(response.status_code, 201)
        record = DeploymentRecord.objects.get(user=self.user)
        self.assertEqual(record.deployment_status, DeploymentStatus.RUNNING)
        self.assertEqual(record.instance_id, "i-life1")

        # No lifecycle action is ever issued by the pipeline.
        mock_provider.terminate_instance.assert_not_called()
        mock_provider.stop_instance.assert_not_called()
        mock_provider.start_instance.assert_not_called()

        messages = [entry.get("message", "") for entry in record.logs]
        self.assertTrue(
            any("keeping EC2 i-life1 running" in message for message in messages),
            messages,
        )
        self.assertFalse(
            any("Terminating" in message for message in messages),
            messages,
        )


class LifecycleEndpointTests(TestCase):
    """TEST 2/3/4 — stop, start and the single destroy endpoint."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="lifecycleapi", password="pass1234", email="lcapi@test.com"
        )
        _make_connection(self.user)
        self.client.force_authenticate(user=self.user)

    @patch("api.views.AwsEc2Provider")
    def test_stop_stops_the_instance_and_never_terminates(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.stop_instance.return_value = {
            "instance_id": "i-life1",
            "region": "ap-south-1",
            "state": "stopped",
            "stopped": True,
            "message": "Stop requested for i-life1.",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)

        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["instanceStopped"])
        self.assertFalse(response.data["data"]["instanceTerminated"])
        mock_provider.stop_instance.assert_called_once_with("i-life1")
        mock_provider.terminate_instance.assert_not_called()

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.STOPPED)

    @patch("api.views.AwsEc2Provider")
    def test_start_starts_the_instance_and_returns_to_running(
        self, mock_provider_cls
    ):
        mock_provider = MagicMock()
        mock_provider.start_instance.return_value = {
            "instance_id": "i-life1",
            "region": "ap-south-1",
            "state": "running",
            "started": True,
            "public_ip": "13.232.1.44",
            "message": "Start requested for i-life1.",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider
        record = _make_record(self.user, deployment_status=DeploymentStatus.STOPPED)

        response = self.client.post(f"/api/deployments/{record.pk}/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["deploymentStatus"], DeploymentStatus.RUNNING)
        self.assertEqual(response.data["data"]["ipAddress"], "13.232.1.44")
        mock_provider.start_instance.assert_called_once_with("i-life1")
        mock_provider.terminate_instance.assert_not_called()

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.RUNNING)
        self.assertEqual(record.ip_address, "13.232.1.44")

    @patch("api.views.AwsEc2Provider")
    def test_start_is_refused_while_the_pipeline_is_in_flight(
        self, mock_provider_cls
    ):
        record = _make_record(self.user, deployment_status=DeploymentStatus.BUILDING)

        response = self.client.post(f"/api/deployments/{record.pk}/start")

        self.assertEqual(response.status_code, 409)
        mock_provider_cls.assert_not_called()

    @patch("api.views.AwsEc2Provider")
    def test_terminate_is_the_only_endpoint_that_destroys(
        self, mock_provider_cls
    ):
        mock_provider = MagicMock()
        mock_provider.terminate_instance.return_value = {
            "instance_id": "i-life1",
            "region": "ap-south-1",
            "state": "terminated",
            "message": "Termination requested for i-life1.",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)

        response = self.client.post(f"/api/deployments/{record.pk}/terminate")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["data"]["deploymentStatus"], DeploymentStatus.TERMINATED
        )
        mock_provider.terminate_instance.assert_called_once_with("i-life1")

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.TERMINATED)
        messages = [entry.get("message", "") for entry in record.logs]
        self.assertTrue(
            any(
                "User requested destruction for deployment" in message
                for message in messages
            ),
            messages,
        )

    @patch("api.views.AwsEc2Provider")
    def test_stop_on_a_stopped_deployment_is_refused(self, mock_provider_cls):
        record = _make_record(self.user, deployment_status=DeploymentStatus.STOPPED)

        response = self.client.post(f"/api/deployments/{record.pk}/stop")

        self.assertEqual(response.status_code, 409)
        mock_provider_cls.assert_not_called()


class StateMachineGuardTests(TestCase):
    """TEST 5 — RUNNING/STOPPED never transition to TERMINATED on their own."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="guardsm", password="pass1234", email="guardsm@test.com"
        )

    def test_running_record_is_never_terminated_by_a_late_write(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)

        changed = set_status(
            str(record.pk),
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.COMPLETED,
            message="cleanup after the run",
        )

        self.assertFalse(changed)
        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.RUNNING)

    def test_running_to_terminated_is_allowed_only_after_an_explicit_stop(self):
        record = _make_record(
            self.user,
            deployment_status=DeploymentStatus.RUNNING,
            cancel_requested=True,
        )

        changed = set_status(
            str(record.pk),
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.COMPLETED,
            message="stopped by the user",
        )

        self.assertTrue(changed)
        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.TERMINATED)

    def test_stopped_record_is_frozen(self):
        record = _make_record(self.user, deployment_status=DeploymentStatus.STOPPED)

        for target in (
            DeploymentStatus.TERMINATED,
            DeploymentStatus.FAILED,
            DeploymentStatus.RUNNING,
            DeploymentStatus.BUILDING,
        ):
            self.assertFalse(
                set_status(
                    str(record.pk),
                    target,
                    stage=DeploymentStage.COMPLETED,
                    message=f"winding-down write to {target}",
                ),
                f"STOPPED → {target} must be refused",
            )

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.STOPPED)

    def test_explicit_user_actions_stay_valid_transitions(self):
        # The API keeps its explicit edges: stop, destroy and start.
        self.assertTrue(
            is_valid_transition(DeploymentStatus.RUNNING, DeploymentStatus.STOPPED)
        )
        self.assertTrue(
            is_valid_transition(DeploymentStatus.RUNNING, DeploymentStatus.TERMINATED)
        )
        self.assertTrue(
            is_valid_transition(DeploymentStatus.STOPPED, DeploymentStatus.RUNNING)
        )
        self.assertTrue(
            is_valid_transition(DeploymentStatus.STOPPED, DeploymentStatus.TERMINATED)
        )


class ProviderWorkerGuardTests(TestCase):
    """TEST 6 — the provider refuses lifecycle actions from the worker."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="guardworker", password="pass1234", email="guardworker@test.com"
        )
        self.connection = _make_connection(self.user)
        self.provider = AwsEc2Provider(user=self.user, connection=self.connection)

    def test_terminate_refused_inside_the_deployment_worker(self):
        with patch.object(self.provider, "get_session") as mock_session:
            with self.assertRaises(AwsEc2Error) as ctx:
                with deployment_worker():
                    self.provider.terminate_instance("i-life1")

        self.assertIn(
            "Refusing automatic infrastructure termination", str(ctx.exception)
        )
        mock_session.assert_not_called()
        self.assertFalse(in_deployment_worker())

    def test_stop_and_start_refused_inside_the_deployment_worker(self):
        for action in (self.provider.stop_instance, self.provider.start_instance):
            with patch.object(self.provider, "get_session") as mock_session:
                with self.assertRaises(AwsEc2Error) as ctx:
                    with deployment_worker():
                        action("i-life1")
                self.assertIn(
                    "Refusing automatic infrastructure", str(ctx.exception)
                )
                mock_session.assert_not_called()

    def test_explicit_terminate_outside_the_worker_still_works(self):
        ec2 = MagicMock()
        session = MagicMock()
        session.client.return_value = ec2

        with patch.object(self.provider, "get_session", return_value=session), patch.object(
            AwsEc2Provider, "_describe_instance", return_value=_running_instance()
        ):
            result = self.provider.terminate_instance("i-life1")

        ec2.terminate_instances.assert_called_once_with(InstanceIds=["i-life1"])
        self.assertEqual(result["state"], "terminated")


class ProviderStopStartTests(TestCase):
    """The provider's stop/start map to StopInstances/StartInstances only."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="providerlc", password="pass1234", email="providerlc@test.com"
        )
        self.connection = _make_connection(self.user)
        self.provider = AwsEc2Provider(user=self.user, connection=self.connection)
        self.ec2 = MagicMock()
        session = MagicMock()
        session.client.return_value = self.ec2
        self.session = session

    def test_stop_instance_calls_stop_instances_not_terminate(self):
        with patch.object(self.provider, "get_session", return_value=self.session), patch.object(
            AwsEc2Provider, "_describe_instance", return_value=_running_instance()
        ):
            result = self.provider.stop_instance("i-life1")

        self.ec2.stop_instances.assert_called_once_with(InstanceIds=["i-life1"])
        self.ec2.terminate_instances.assert_not_called()
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(result["stopped"])

    def test_stop_instance_refuses_an_instance_it_does_not_manage(self):
        with patch.object(self.provider, "get_session", return_value=self.session), patch.object(
            AwsEc2Provider,
            "_describe_instance",
            return_value=_running_instance(tag="SomebodyElse"),
        ):
            with self.assertRaises(AwsEc2Error):
                self.provider.stop_instance("i-life1")

        self.ec2.stop_instances.assert_not_called()
        self.ec2.terminate_instances.assert_not_called()

    def test_start_instance_calls_start_instances_not_terminate(self):
        stopped = _running_instance()
        stopped["State"] = {"Name": "stopped"}
        stopped.pop("PublicIpAddress", None)

        with patch.object(self.provider, "get_session", return_value=self.session), patch.object(
            AwsEc2Provider, "_describe_instance", return_value=stopped
        ):
            result = self.provider.start_instance("i-life1")

        self.ec2.start_instances.assert_called_once_with(InstanceIds=["i-life1"])
        self.ec2.terminate_instances.assert_not_called()
        self.ec2.get_waiter.assert_any_call("instance_running")
        self.assertEqual(result["state"], "running")
        self.assertTrue(result["started"])


class RollbackRetainsInstanceTests(TestCase):
    """TEST 7 — rollback keeps the instance (it only stops the app)."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="rollbacklc", password="pass1234", email="rollbacklc@test.com"
        )
        _make_connection(self.user)
        self.client.force_authenticate(user=self.user)

    @patch("api.views.AwsEc2Provider")
    def test_rollback_never_terminates_the_instance(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.rollback.return_value = {
            "status": DeploymentStatus.ROLLED_BACK,
            "message": "Application containers stopped; instance retained.",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider
        record = _make_record(self.user, deployment_status=DeploymentStatus.RUNNING)

        response = self.client.post(f"/api/deployments/{record.pk}/rollback")

        self.assertEqual(response.status_code, 200)
        mock_provider.rollback.assert_called_once_with("i-life1")
        mock_provider.terminate_instance.assert_not_called()
        mock_provider.stop_instance.assert_not_called()

        record.refresh_from_db()
        self.assertEqual(record.deployment_status, DeploymentStatus.ROLLED_BACK)


class SourceLevelGuardTests(TestCase):
    """TEST 8 — regressions are caught even if the wiring is rewritten."""

    def test_pipeline_never_calls_the_lifecycle_apis(self):
        source = (_BACKEND / "services" / "deployment" / "pipeline.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("terminate_instance", "stop_instance(", "start_instance("):
            self.assertNotIn(
                forbidden,
                source,
                f"the deployment pipeline must never call {forbidden}",
            )

    def test_only_the_destroy_endpoint_terminates(self):
        source = (_BACKEND / "views.py").read_text(encoding="utf-8")

        self.assertEqual(
            source.count("terminate_instance"),
            1,
            "TerminateInstances must only be reachable from the destroy view",
        )
        terminate_view = source.index("def deployment_terminate_view")
        call_site = source.index("terminate_instance")
        self.assertLess(terminate_view, call_site)

        stop_view = source.index("def deployment_stop_view")
        start_view = source.index("def deployment_start_view")
        self.assertLess(stop_view, start_view)
        self.assertNotIn(
            "terminate_instance",
            source[stop_view:start_view],
            "stop must never terminate the instance",
        )
        self.assertNotIn(
            "terminate_instance",
            source[start_view : source.index("def deployment_rollback_view")],
            "start must never terminate the instance",
        )

    def test_provider_exposes_stop_and_start(self):
        source = (_BACKEND / "services" / "deployment" / "aws_ec2_provider.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def stop_instance(", source)
        self.assertIn("def start_instance(", source)
        # the only raw TerminateInstances calls are the destroy path and
        # the pre-deploy SSM recovery of a never-healthy instance
        self.assertEqual(source.count("ec2.terminate_instances("), 2)

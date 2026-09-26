"""
Part 5 — final AWS deployment integration tests.

Covers deploy_view retirement of Vercel/Render, env validation,
provision/container failure paths, and repository-limit handling.
"""

from unittest.mock import patch, MagicMock
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from api.models import AWSConnection, DeploymentRecord, GitHubConnection, Project
from api.services.deployment.aws_ec2_provider import AwsEc2Error

User = get_user_model()


class DeployRetiredProviderTests(TestCase):
    """Vercel/Render are isolated: new deploys rejected with 400 RETIRED."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="retired", password="pass1234", email="retired@example.com"
        )
        self.client.force_authenticate(user=self.user)

    def _post(self, provider):
        return self.client.post(
            "/api/deploy",
            {
                "environmentName": "x-prod",
                "provider": provider,
                "monthlyCost": 0,
                "specs": {},
                "envVars": {},
            },
            format="json",
        )

    def test_vercel_rejected_with_400_retired(self):
        response = self._post("Vercel")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "RETIRED")
        self.assertEqual(response.data["supported"], ["AWS"])
        self.assertEqual(response.data["connectUrl"], "/connect-aws")
        self.assertIn("AWS EC2", response.data["error"])

    def test_render_rejected_with_400_retired(self):
        response = self._post("Render")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["status"], "RETIRED")


class DeployEnvValidationTests(TestCase):
    """Missing required env vars and invalid DATABASE_URL schemes → 400."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="envuser", password="pass1234", email="env@example.com"
        )
        self.project = Project.objects.create(
            user=self.user,
            name="Env Demo",
            github_repo={"name": "demo/env-demo", "default_branch": "main"},
        )
        GitHubConnection.objects.create(
            user=self.user,
            access_token="gh-token",
            github_user_id="1",
            github_login="demo",
        )
        AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-x",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        self.client.force_authenticate(user=self.user)

    def _post(self, env_vars, files=None):
        body = {
            "projectId": self.project.id,
            "environmentName": "env-prod",
            "provider": "AWS",
            "monthlyCost": 0,
            "specs": {},
            "region": "ap-south-1",
            "envVars": env_vars,
        }
        with patch(
            "api.services.github_repository_service.inspect_repository"
        ) as mock_inspect:
            mock_inspect.return_value = {
                "files": files or {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
                "tree": [],
                "has_dockerfile": False,
                "has_cicd": False,
            }
            response = self.client.post("/api/deploy", body, format="json")
        return response

    def test_missing_required_env_var_returns_400(self):
        files = {
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
            ".env.example": "SECRET_KEY=changeme\n",
        }
        response = self._post({}, files=files)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "MISSING_ENV_VARS")
        self.assertIn("SECRET_KEY", response.data["missing"])

    @override_settings(
        AWS_ALLOWED_DB_URL_SCHEMES=("postgres://", "postgresql://", "mysql://")
    )
    def test_invalid_database_url_scheme_returns_400(self):
        files = {
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
            ".env.example": "DATABASE_URL=sqlite:///db.sqlite3\n",
        }
        response = self._post({"DATABASE_URL": "sqlite:///db.sqlite3"}, files=files)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "INVALID_DATABASE_URL")
        self.assertEqual(response.data["field"], "DATABASE_URL")

    @override_settings(
        AWS_ALLOWED_DB_URL_SCHEMES=("postgres://", "postgresql://", "mysql://")
    )
    @override_settings(DEPLOYMENT_RUN_INLINE=True)
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    def test_valid_database_url_scheme_passes_validation(
        self, mock_provider_cls, _sts
    ):
        files = {
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
            ".env.example": "DATABASE_URL=postgres://user:pass@db:5432/app\n",
        }
        mock_provider = MagicMock()
        mock_provider.start.return_value = {
            "instance_id": "i-0dbok",
            "deployment_id": "i-0dbok",
            "status": "RUNNING",
            "public_ip": "13.232.1.77",
            "instance_type": "t3.micro",
            "region": "ap-south-1",
            "reused": False,
            "logs": [],
        }
        mock_provider.deploy.return_value = {
            "instance_id": "i-0dbok",
            "deployment_id": "i-0dbok",
            "status": "RUNNING",
            "endpoint_url": "http://13.232.1.77",
            "public_ip": "13.232.1.77",
            "region": "ap-south-1",
            "logs": [],
        }
        mock_provider_cls.return_value = mock_provider

        with patch(
            "api.services.github_repository_service.inspect_repository"
        ) as mock_inspect:
            mock_inspect.return_value = {"files": files, "tree": []}
            response = self.client.post(
                "/api/deploy",
                {
                    "projectId": self.project.id,
                    "environmentName": "env-prod",
                    "provider": "AWS",
                    "envVars": {
                        "DATABASE_URL": "postgres://user:pass@db:5432/app"
                    },
                },
                format="json",
            )
        # Env validation passed, so the record was created and queued —
        # a validation failure would have returned 400 with no record.
        self.assertEqual(response.status_code, 201)
        record = DeploymentRecord.objects.get(user=self.user)
        self.assertEqual(record.deployment_status, "RUNNING")
        self.assertEqual(record.live_url, "http://13.232.1.77")


class DeployFailurePathTests(TestCase):
    """Provision and container-deploy failures are recorded by the pipeline."""

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="failuser", password="pass1234", email="fail@example.com"
        )
        self.project = Project.objects.create(
            user=self.user,
            name="Fail Demo",
            github_repo={"name": "demo/fail-demo", "default_branch": "main"},
        )
        GitHubConnection.objects.create(
            user=self.user,
            access_token="gh-token",
            github_user_id="2",
            github_login="demo",
        )
        AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-x",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )
        self.client.force_authenticate(user=self.user)

    def _deploy(self):
        with patch(
            "api.services.github_repository_service.inspect_repository"
        ) as mock_inspect:
            mock_inspect.return_value = {
                "files": {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
                "tree": [],
            }
            return self.client.post(
                "/api/deploy",
                {
                    "projectId": self.project.id,
                    "environmentName": "fail-prod",
                    "provider": "AWS",
                    "envVars": {},
                },
                format="json",
            )

    @override_settings(DEPLOYMENT_RUN_INLINE=True)
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    def test_provision_failure_marks_record_failed(self, mock_provider_cls, _sts):
        mock_provider = MagicMock()
        mock_provider.start.side_effect = AwsEc2Error(
            "missing a required EC2 permission"
        )
        mock_provider_cls.return_value = mock_provider

        response = self._deploy()

        self.assertEqual(response.status_code, 201)
        record = DeploymentRecord.objects.get(user=self.user)
        self.assertEqual(record.deployment_status, "FAILED")
        self.assertEqual(record.provider, "AWS")
        self.assertTrue(
            any(
                "missing a required EC2 permission" in e.get("message", "")
                for e in record.logs
            )
        )
        mock_provider.deploy.assert_not_called()

    @override_settings(DEPLOYMENT_RUN_INLINE=True)
    @patch("api.services.deployment.pipeline.assume_role_credentials")
    @patch("api.services.deployment.pipeline.AwsEc2Provider")
    def test_container_deploy_failure_marks_record_failed(
        self, mock_provider_cls, _sts
    ):
        mock_provider = MagicMock()
        mock_provider.start.return_value = {
            "instance_id": "i-0fail1",
            "deployment_id": "i-0fail1",
            "status": "RUNNING",
            "public_ip": "13.232.1.99",
            "region": "ap-south-1",
            "logs": [],
        }
        mock_provider.deploy.side_effect = AwsEc2Error(
            "docker compose failed on instance"
        )
        mock_provider_cls.return_value = mock_provider

        response = self._deploy()

        self.assertEqual(response.status_code, 201)
        record = DeploymentRecord.objects.get(user=self.user)
        self.assertEqual(record.deployment_status, "FAILED")
        self.assertEqual(record.instance_id, "i-0fail1")
        self.assertTrue(
            any(
                "docker compose failed" in e.get("message", "")
                for e in record.logs
            )
        )
        mock_provider.start.assert_called_once()


class DeployOwnershipTests(TestCase):
    """Deploy and management endpoints enforce ownership."""

    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="owner", password="pass1234", email="owner@example.com"
        )
        self.intruder = User.objects.create_user(
            username="intruder", password="pass1234", email="intruder@example.com"
        )
        self.connection = AWSConnection.objects.create(
            user=self.owner,
            role_arn="arn:aws:iam::111122223333:role/CloudWiseDeployRole",
            external_id="cloudwise-own",
            account_id="111122223333",
            region="ap-south-1",
            status="active",
        )
        self.record = DeploymentRecord.objects.create(
            user=self.owner,
            environment_name="own-prod",
            provider="AWS",
            provider_deployment_id="i-own1",
            instance_id="i-own1",
            aws_account_id="111122223333",
            deployment_status="RUNNING",
            ip_address="13.232.1.1",
        )

    def test_status_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        for path in (
            "/api/deployments/i-own1",
            "/api/deployments/i-own1/status",
            "/api/deployments/i-own1/logs",
        ):
            self.assertEqual(self.client.get(path).status_code, 404, path)

    def test_status_requires_authentication(self):
        response = self.client.get("/api/deployments/i-own1/status")
        self.assertIn(response.status_code, (401, 403))

    @patch("api.views.AwsEc2Provider")
    def test_owner_can_read_status(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.get_status.return_value = {
            "deployment_id": "i-own1",
            "status": "RUNNING",
            "progress": 100,
            "provider_type": "AWS",
            "ip_address": "13.232.1.1",
            "instance_state": "running",
            "region": "ap-south-1",
            "message": "ok",
        }
        mock_provider_cls.return_value = mock_provider
        self.client.force_authenticate(user=self.owner)
        response = self.client.get("/api/deployments/i-own1/status")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["deploymentStatus"], "RUNNING")
        self.assertEqual(data["instanceState"], "running")
        self.assertEqual(data["awsAccountId"], "111122223333")

    def test_owner_can_read_detail_and_list(self):
        self.client.force_authenticate(user=self.owner)
        detail = self.client.get("/api/deployments/i-own1")
        self.assertEqual(detail.status_code, 200)
        data = detail.data["data"]
        for key in (
            "id",
            "deploymentStatus",
            "liveUrl",
            "repository",
            "awsAccountId",
            "region",
            "instanceId",
            "progress",
            "openUrl",
        ):
            self.assertIn(key, data)

        listing = self.client.get("/api/deployments")
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["count"], 1)

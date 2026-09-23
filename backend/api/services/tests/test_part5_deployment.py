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
    def test_valid_database_url_scheme_passes_validation(self):
        files = {
            "package.json": '{"dependencies":{"react":"18.3.1"}}',
            ".env.example": "DATABASE_URL=postgres://user:pass@db:5432/app\n",
        }
        with patch("api.views.AwsEc2Provider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.start.side_effect = AwsEc2Error("no permissions for ec2")
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
        # Passes env validation; fails later at provision (502) — not 400
        self.assertEqual(response.status_code, 502)


class DeployFailurePathTests(TestCase):
    """Provision and container-deploy failures return 502 with FAILED record."""

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

    @patch("api.views.AwsEc2Provider")
    def test_provision_failure_returns_502_and_failed_record(self, mock_provider_cls):
        mock_provider = MagicMock()
        mock_provider.start.side_effect = AwsEc2Error(
            "missing a required EC2 permission"
        )
        mock_provider_cls.return_value = mock_provider

        response = self._deploy()

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.data["success"])
        self.assertIn("EC2 permission", response.data["error"])
        record = DeploymentRecord.objects.filter(
            user=self.user, provider="AWS", status="FAILED"
        ).first()
        self.assertIsNotNone(record)
        mock_provider.deploy.assert_not_called()

    @patch("api.views.AwsEc2Provider")
    def test_container_deploy_failure_returns_502_and_failed_record(
        self, mock_provider_cls
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

        self.assertEqual(response.status_code, 502)
        self.assertFalse(response.data["success"])
        self.assertIn("docker compose failed", response.data["error"])
        record = DeploymentRecord.objects.filter(
            user=self.user, provider="AWS", status="FAILED"
        ).first()
        self.assertIsNotNone(record)
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
        self.record = DeploymentRecord.objects.create(
            user=self.owner,
            environment_name="own-prod",
            provider="AWS",
            provider_deployment_id="i-own1",
            status="RUNNING",
            ip_address="13.232.1.1",
        )

    def test_status_hidden_from_non_owner(self):
        self.client.force_authenticate(user=self.intruder)
        response = self.client.get("/api/deployments/i-own1/status")
        self.assertEqual(response.status_code, 404)

    def test_status_requires_authentication(self):
        response = self.client.get("/api/deployments/i-own1/status")
        self.assertIn(response.status_code, (401, 403))

    def test_owner_can_read_status(self):
        self.client.force_authenticate(user=self.owner)
        with patch("api.views.AwsEc2Provider") as mock_provider_cls:
            mock_provider = MagicMock()
            mock_provider.get_status.return_value = {
                "deployment_id": "i-own1",
                "status": "RUNNING",
                "progress": 100,
                "provider_type": "AWS",
                "endpoint_url": None,
                "ip_address": "13.232.1.1",
                "instance_state": "running",
                "region": "ap-south-1",
                "message": "ok",
            }
            mock_provider_cls.return_value = mock_provider
            response = self.client.get("/api/deployments/i-own1/status")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"]["status"], "RUNNING")

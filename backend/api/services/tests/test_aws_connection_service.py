"""
Tests for the AWS account connection service (Part 3).

Covers: least-privilege policy generation (no AdministratorAccess),
External ID trust condition, role ARN validation, STS validation flow,
minimum stored connection information (no long-lived access keys).
"""

from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import AWSConnection
from api.services.deployment.aws_connection_service import (
    AwsConnectionError,
    build_policies,
    connect,
    connection_public_dict,
    disconnect,
    ensure_pending_connection,
    generate_external_id,
)

User = get_user_model()


class TrustAndPermissionsPolicyTests(TestCase):
    def setUp(self):
        self.policies = build_policies("cloudwise-user-1-abc123", "111122223333")

    def test_trust_policy_requires_external_id_condition(self):
        self.assertIn("sts:ExternalId", self.policies["trustPolicy"])
        self.assertIn("cloudwise-user-1-abc123", self.policies["trustPolicy"])
        self.assertIn("sts:AssumeRole", self.policies["trustPolicy"])
        self.assertIn("arn:aws:iam::111122223333:root", self.policies["trustPolicy"])

    def test_permissions_policy_is_least_privilege(self):
        policy = self.policies["permissionsPolicy"]
        # Required deployment capabilities present
        self.assertIn("ec2:DescribeInstances", policy)
        self.assertIn("ec2:RunInstances", policy)
        self.assertIn("ec2:CreateSecurityGroup", policy)
        self.assertIn("ec2:AuthorizeSecurityGroupIngress", policy)
        self.assertIn("ec2:CreateTags", policy)
        # SSM for container deploy (Part 4/5) — still not blanket admin
        self.assertIn("ssm:SendCommand", policy)
        self.assertIn("ssm:GetCommandInvocation", policy)
        # Never AdministratorAccess / blanket permissions
        self.assertNotIn("AdministratorAccess", policy)
        self.assertNotIn('"Action": "*"', policy)
        self.assertNotIn('"Action": "*:*"', policy)
        self.assertNotIn("Action\": \"*", policy)

    def test_instructions_cover_role_creation(self):
        instructions = " ".join(self.policies["instructions"])
        self.assertIn("External ID", instructions)
        self.assertIn("least-privilege", instructions)
        self.assertIn("ARN", instructions)

    def test_no_secrets_in_policies(self):
        blob = str(self.policies)
        self.assertNotIn("SecretAccessKey", blob)
        self.assertNotIn("AWS_SECRET", blob)


class ExternalIdTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="awsuser", password="pass1234", email="aws@example.com"
        )

    def test_external_id_is_unique_per_generation(self):
        a = generate_external_id(self.user)
        b = generate_external_id(self.user)
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith(f"cloudwise-{self.user.id}-"))

    def test_ensure_pending_connection_creates_once(self):
        first = ensure_pending_connection(self.user)
        second = ensure_pending_connection(self.user)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(first.status, "pending")
        self.assertTrue(first.external_id)


class ConnectValidationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="awsconn", password="pass1234", email="conn@example.com"
        )

    def test_invalid_role_arn_rejected_before_any_sts_call(self):
        with patch(
            "api.services.deployment.aws_connection_service.get_session"
        ) as mock_session:
            with self.assertRaises(AwsConnectionError):
                connect(self.user, "not-an-arn")
            mock_session.assert_not_called()

    def test_connect_success_stores_minimum_information(self):
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
            connection = connect(
                self.user,
                "arn:aws:iam::999988887777:role/CloudWiseDeployRole",
                region="ap-south-1",
            )

        self.assertEqual(connection.status, "active")
        self.assertEqual(connection.account_id, "999988887777")
        self.assertEqual(
            connection.role_arn,
            "arn:aws:iam::999988887777:role/CloudWiseDeployRole",
        )
        # Minimum connection info only — no credential fields exist at all
        field_names = [f.name for f in AWSConnection._meta.get_fields()]
        for forbidden in (
            "access_key",
            "access_key_id",
            "secret_access_key",
            "secret_key",
            "session_token",
            "credentials",
        ):
            self.assertNotIn(forbidden, field_names)
        # Only the expected fields are stored
        self.assertCountEqual(
            field_names,
            [
                "id",
                "user",
                "role_arn",
                "external_id",
                "account_id",
                "region",
                "status",
                "connected_at",
                "updated_at",
                "deployment_records",
            ],
        )
        # AssumeRole was called with the External ID (confused-deputy protection)
        # (session was pre-built in this test; covered in provider tests)

    def test_connect_failure_propagates_as_connection_error(self):
        with patch(
            "api.services.deployment.aws_connection_service.get_session",
            side_effect=AwsConnectionError("Access denied assuming the IAM role."),
        ):
            with self.assertRaises(AwsConnectionError):
                connect(
                    self.user,
                    "arn:aws:iam::999988887777:role/CloudWiseDeployRole",
                )

    def test_connection_public_dict_has_no_secrets(self):
        connection = ensure_pending_connection(self.user)
        connection.role_arn = "arn:aws:iam::999988887777:role/CloudWiseDeployRole"
        connection.account_id = "999988887777"
        connection.status = "active"
        connection.save()

        payload = connection_public_dict(connection)
        self.assertTrue(payload["connected"])
        self.assertEqual(payload["accountId"], "999988887777")
        blob = str(payload).lower()
        self.assertNotIn("secret", blob)
        self.assertNotIn("session_token", blob)
        self.assertNotIn("access_key", blob)

    def test_disconnect_removes_connection(self):
        ensure_pending_connection(self.user)
        self.assertTrue(disconnect(self.user))
        self.assertFalse(
            AWSConnection.objects.filter(user=self.user).exists()
        )

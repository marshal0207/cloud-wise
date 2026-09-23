"""
AWS account connection service — IAM role authorization with temporary
(STS) credentials.

Architecture
------------
* CloudWise NEVER asks users for permanent AWS access keys and NEVER
  stores long-lived AWS secret keys for a connection.
* The user creates an IAM role in their OWN AWS account with:
  - a trust policy allowing sts:AssumeRole from CloudWise's AWS account,
    restricted by a per-user sts:ExternalId (confused-deputy protection);
  - a least-privilege permissions policy for EC2 deployment operations
    (never AdministratorAccess).
* A stored AWSConnection holds only: role_arn, external_id, account_id,
  region — the minimum required connection information.
* At operation time CloudWise calls sts:AssumeRole to obtain SHORT-LIVED
  credentials (default 1 hour) that are used in-memory and never persisted.

Endpoints served by views.aws_*_view:
  GET  /api/aws/connect-info   → policies + external id to create the role
  POST /api/aws/connect        → validate role ARN via AssumeRole
  GET  /api/aws/connection     → connection status (no secrets)
  POST /api/aws/disconnect     → remove the connection
"""

from __future__ import annotations

import json
import re
import uuid

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError

from django.conf import settings

from ...models import AWSConnection

ROLE_ARN_RE = re.compile(r"^arn:aws[a-zA-Z-]*:iam::\d{12}:role/.+$")

# Least-privilege deployment permissions — EC2 describe/create/reuse,
# security-group configuration, instance metadata and required tagging.
# Explicitly NOT AdministratorAccess.
LEAST_PRIVILEGE_STATEMENTS: list[dict] = [
    {
        "Sid": "CloudWiseEC2Describe",
        "Effect": "Allow",
        "Action": [
            "ec2:DescribeInstances",
            "ec2:DescribeInstanceStatus",
            "ec2:DescribeImages",
            "ec2:DescribeSecurityGroups",
            "ec2:DescribeVpcs",
            "ec2:DescribeSubnets",
            "ec2:DescribeKeyPairs",
            "ec2:DescribeAvailabilityZones",
            "ec2:DescribeTags",
            "ec2:DescribeVolumes",
        ],
        "Resource": "*",
    },
    {
        "Sid": "CloudWiseEC2Provision",
        "Effect": "Allow",
        "Action": [
            "ec2:RunInstances",
            "ec2:StartInstances",
            "ec2:StopInstances",
            "ec2:RebootInstances",
            "ec2:TerminateInstances",
            "ec2:CreateTags",
        ],
        "Resource": "*",
    },
    {
        "Sid": "CloudWiseSecurityGroupConfig",
        "Effect": "Allow",
        "Action": [
            "ec2:CreateSecurityGroup",
            "ec2:AuthorizeSecurityGroupIngress",
            "ec2:AuthorizeSecurityGroupEgress",
            "ec2:RevokeSecurityGroupIngress",
            "ec2:ModifyInstanceAttribute",
        ],
        "Resource": "*",
    },
    {
        "Sid": "CloudWisePassInstanceRole",
        "Effect": "Allow",
        "Action": "iam:PassRole",
        "Resource": "arn:aws:iam::*:role/cloudwise-ec2-*",
        "Condition": {"StringEquals": {"iam:PassedToService": "ec2.amazonaws.com"}},
    },
    {
        "Sid": "CloudWiseReadPublicAmiParameter",
        "Effect": "Allow",
        "Action": ["ssm:GetParameter", "ssm:GetParameters"],
        "Resource": "arn:aws:ssm:*:aws:parameter/aws/service/ami-amazon-linux-latest/*",
    },
    {
        "Sid": "CloudWiseSsmContainerDeploy",
        "Effect": "Allow",
        "Action": [
            "ssm:SendCommand",
            "ssm:GetCommandInvocation",
            "ssm:ListCommands",
            "ssm:DescribeInstanceInformation",
            "ssm:DescribeInstanceAssociations",
        ],
        "Resource": "*",
    },
]


class AwsConnectionError(Exception):
    """Raised when AWS authorization / connection validation fails."""


def generate_external_id(user) -> str:
    """Per-user External ID — protects against the confused-deputy problem."""
    return f"cloudwise-{user.id}-{uuid.uuid4().hex[:16]}"


def platform_credentials_configured() -> bool:
    """True when explicit CloudWise platform deployer keys are configured."""
    return bool(
        settings.AWS_DEPLOYER_ACCESS_KEY_ID
        and settings.AWS_DEPLOYER_SECRET_ACCESS_KEY
    )


def get_platform_session() -> boto3.Session:
    """
    CloudWise platform session used to call sts:AssumeRole.

    Uses the server-side deployer keys when configured, otherwise the
    boto3 default credential chain (environment / instance role).
    """
    if platform_credentials_configured():
        return boto3.Session(
            aws_access_key_id=settings.AWS_DEPLOYER_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_DEPLOYER_SECRET_ACCESS_KEY,
            region_name=settings.AWS_DEPLOYER_REGION,
        )
    return boto3.Session(region_name=settings.AWS_DEPLOYER_REGION)


def get_platform_account_id() -> str:
    """Resolve CloudWise's AWS account id (setting first, then STS)."""
    if settings.AWS_TRUSTED_ACCOUNT_ID:
        return settings.AWS_TRUSTED_ACCOUNT_ID
    try:
        sts = get_platform_session().client("sts")
        return str(sts.get_caller_identity().get("Account", ""))
    except (ClientError, BotoCoreError, NoCredentialsError):
        return ""


def _friendly_sts_error(exc: Exception) -> str:
    if isinstance(exc, NoCredentialsError):
        return (
            "CloudWise platform AWS credentials are not configured. "
            "Set AWS_DEPLOYER_ACCESS_KEY_ID / AWS_DEPLOYER_SECRET_ACCESS_KEY "
            "in backend/.env so CloudWise can assume your IAM role."
        )
    code = ""
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", ""))
    if code in ("AccessDenied", "AccessDeniedException"):
        return (
            "Access denied assuming the IAM role. Verify the role trust "
            "policy allows CloudWise's account and matches this "
            "connection's External ID."
        )
    if code in ("MalformedPolicyDocument", "InvalidParameterValue"):
        return f"Invalid IAM role configuration: {exc}"
    return f"Failed to assume IAM role: {exc}"


def assume_role_credentials(connection: AWSConnection) -> dict:
    """
    Call sts:AssumeRole for the user's role and return temporary
    credentials. The credentials are returned in-memory only and must
    never be persisted or logged.
    """
    if not connection.role_arn:
        raise AwsConnectionError("No IAM role ARN stored for this AWS connection.")
    sts = get_platform_session().client("sts")
    try:
        response = sts.assume_role(
            RoleArn=connection.role_arn,
            RoleSessionName=(
                f"{settings.AWS_ROLE_SESSION_NAME}-{connection.user_id}"
            )[:64],
            ExternalId=connection.external_id,
            DurationSeconds=settings.AWS_ROLE_DURATION_SECONDS,
        )
    except (ClientError, BotoCoreError, NoCredentialsError) as exc:
        raise AwsConnectionError(_friendly_sts_error(exc)) from exc
    creds = response["Credentials"]
    return {
        "aws_access_key_id": creds["AccessKeyId"],
        "aws_secret_access_key": creds["SecretAccessKey"],
        "aws_session_token": creds["SessionToken"],
    }


def get_session(connection: AWSConnection) -> boto3.Session:
    """boto3 session bound to temporary credentials for the user's account."""
    credentials = assume_role_credentials(connection)
    return boto3.Session(
        **credentials,
        region_name=connection.region or settings.AWS_DEFAULT_REGION,
    )


def build_policies(
    external_id: str, trusted_account_id: str | None = None
) -> dict:
    """
    Build the trust + least-privilege permissions policies the user pastes
    into AWS IAM when creating their deployment role.
    """
    account = trusted_account_id or get_platform_account_id()
    if not account:
        account = "<CLOUDWISE_AWS_ACCOUNT_ID>"

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "CloudWiseAssumeRoleWithExternalId",
                "Effect": "Allow",
                "Principal": {"AWS": f"arn:aws:iam::{account}:root"},
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"sts:ExternalId": external_id}
                },
            }
        ],
    }
    permissions_policy = {
        "Version": "2012-10-17",
        "Statement": LEAST_PRIVILEGE_STATEMENTS,
    }
    return {
        "externalId": external_id,
        "trustedAccountId": account,
        "trustPolicy": json.dumps(trust_policy, indent=2),
        "permissionsPolicy": json.dumps(permissions_policy, indent=2),
        "instructions": [
            "Open the AWS console → IAM → Roles → Create role.",
            "Trusted entity type: AWS account → Another AWS account.",
            f"Account ID: {account} (CloudWise deployer account).",
            "Paste the trust policy above (it enforces your unique External ID).",
            "Attach the least-privilege permissions policy above (no AdministratorAccess).",
            "Name the role (e.g. CloudWiseDeployRole) and create it.",
            "Copy the new role's ARN and paste it into CloudWise below.",
        ],
    }


def ensure_pending_connection(user) -> AWSConnection:
    """Get or create a pending connection that owns a unique External ID."""
    connection, _created = AWSConnection.objects.get_or_create(
        user=user,
        defaults={
            "role_arn": "",
            "external_id": generate_external_id(user),
            "status": "pending",
            "region": settings.AWS_DEFAULT_REGION,
        },
    )
    if not connection.external_id:
        connection.external_id = generate_external_id(user)
        connection.save(update_fields=["external_id"])
    return connection


def connect(user, role_arn: str, region: str | None = None) -> AWSConnection:
    """
    Validate and activate an AWS connection.

    Validates by assuming the role with temporary credentials and calling
    sts:GetCallerIdentity. Stores only role ARN + external id + account id.
    """
    role_arn = (role_arn or "").strip()
    if not ROLE_ARN_RE.match(role_arn):
        raise AwsConnectionError(
            "Invalid IAM Role ARN. Expected format: "
            "arn:aws:iam::123456789012:role/CloudWiseDeployRole"
        )

    connection = ensure_pending_connection(user)
    connection.role_arn = role_arn
    if region:
        connection.region = region.strip()
    connection.save(update_fields=["role_arn", "region", "updated_at"])

    # Validate: temporary credentials must work and resolve an account id.
    session = get_session(connection)
    identity = session.client("sts").get_caller_identity()
    connection.account_id = str(identity.get("Account", ""))
    connection.status = "active"
    connection.save(update_fields=["account_id", "status", "updated_at"])
    return connection


def get_active_connection(user) -> AWSConnection | None:
    return AWSConnection.objects.filter(user=user, status="active").first()


def connection_public_dict(connection: AWSConnection | None) -> dict:
    """Safe JSON view of a connection — contains no secrets by design."""
    if connection is None:
        return {"connected": False}
    return {
        "connected": connection.status == "active",
        "status": connection.status,
        "accountId": connection.account_id,
        "roleArn": connection.role_arn,
        "externalId": connection.external_id,
        "region": connection.region,
        "connectedAt": connection.connected_at.isoformat()
        if connection.connected_at
        else None,
    }


def disconnect(user) -> bool:
    """Remove the user's AWS connection (no cloud-side changes needed)."""
    deleted, _ = AWSConnection.objects.filter(user=user).delete()
    return deleted > 0

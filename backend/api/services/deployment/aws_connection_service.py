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
  POST /api/aws/verify         → one real verification phase (identity /
                                 permissions / region) for the checklist
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
from .aws_permissions import (
    generate_external_id,
    get_cloudwise_trust_policy,
    get_cloudwise_permissions_policy,
    get_required_permissions,
)

ROLE_ARN_RE = re.compile(r"^arn:aws[a-zA-Z-]*:iam::\d{12}:role/.+$")


class AwsConnectionError(Exception):
    """
    Raised when AWS authorization / connection validation fails.

    ``message`` is always beginner-friendly and safe to show in the UI.
    ``technical`` (optional) carries the raw AWS/boto3 error and is only
    ever returned inside an explicit "technical details" payload.
    """

    def __init__(self, message: str, technical: str = ""):
        super().__init__(message)
        self.technical = technical


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

    return boto3.Session(
        region_name=settings.AWS_DEPLOYER_REGION
    )


def get_platform_account_id() -> str:
    """Resolve CloudWise's AWS account id (setting first, then STS)."""
    if settings.AWS_TRUSTED_ACCOUNT_ID:
        return settings.AWS_TRUSTED_ACCOUNT_ID

    try:
        sts = get_platform_session().client("sts")
        return str(sts.get_caller_identity().get("Account", ""))
    except (ClientError, BotoCoreError, NoCredentialsError):
        return ""


def _friendly_sts_error(exc: Exception) -> tuple[str, str]:
    """
    Map a raw boto3/sts failure to (beginner message, raw technical text).

    The beginner message never contains botocore type names, stack traces
    or AWS error codes — those live only in the second element, which the
    API returns as an opt-in "technical" field for debugging.
    """
    technical = f"{exc.__class__.__name__}: {exc}"

    if isinstance(exc, NoCredentialsError):
        return (
            "CloudWise could not assume the role because the CloudWise "
            "server is missing its own platform credentials. This is a "
            "server configuration issue, not a problem with your AWS "
            "account.",
            technical,
        )

    code = ""

    if isinstance(exc, ClientError):
        code = str(
            exc.response.get("Error", {}).get("Code", "")
        )

    if code in ("AccessDenied", "AccessDeniedException"):
        return (
            "CloudWise could not assume the role. The role's trust policy "
            "may not contain the CloudWise account ID or the correct "
            "External ID.",
            technical,
        )

    if code in ("MalformedPolicyDocument", "InvalidParameterValue"):
        return (
            "The trust policy on your role is not valid. Re-copy the trust "
            "policy CloudWise generated for this connection and save it on "
            "the role.",
            technical,
        )

    return (
        "CloudWise could not assume the role. The role's trust policy may "
        "not contain the CloudWise account ID or the correct External ID.",
        technical,
    )


def assume_role_credentials(connection: AWSConnection) -> dict:
    """
    Call sts:AssumeRole for the user's role and return temporary
    credentials. The credentials are returned in-memory only and must
    never be persisted or logged.
    """
    if not connection.role_arn:
        raise AwsConnectionError(
            "No IAM role ARN stored for this AWS connection."
        )

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
        message, technical = _friendly_sts_error(exc)
        raise AwsConnectionError(
            message,
            technical=technical,
        ) from exc

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
    external_id: str,
    trusted_account_id: str | None = None,
) -> dict:
    """
    Build the trust + least-privilege permissions policies the user pastes
    into AWS IAM when creating their deployment role.

    Uses the canonical policy generator (aws_permissions) as the single
    source of truth. The frontend receives the policy from this backend
    API — never duplicate the policy manually in React.
    """
    account = trusted_account_id or get_platform_account_id()

    if not account:
        account = "038658707850"

    trust_policy = get_cloudwise_trust_policy(
        external_id,
        account,
    )

    permissions_policy = get_cloudwise_permissions_policy()

    return {
        "externalId": external_id,
        "trustedAccountId": account,
        "trustPolicy": json.dumps(
            trust_policy,
            indent=2,
        ),
        "permissionsPolicy": json.dumps(
            permissions_policy,
            indent=2,
        ),
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

        connection.save(
            update_fields=["external_id"]
        )

    return connection


def connect(
    user,
    role_arn: str,
    region: str | None = None,
) -> AWSConnection:
    """
    Validate and activate an AWS connection.

    Validates by assuming the role with temporary credentials and calling
    sts:GetCallerIdentity. Stores only role ARN + external id + account id.

    After validation, also verifies the selected region is available and
    that the credentials can perform minimum required EC2 operations.
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

    connection.save(
        update_fields=[
            "role_arn",
            "region",
            "updated_at",
        ]
    )

    # Validate: temporary credentials must work and resolve an account id.
    session = get_session(connection)

    identity = session.client("sts").get_caller_identity()

    connection.account_id = str(
        identity.get("Account", "")
    )

    # --- Validate selected AWS region is available ---
    try:
        ec2 = session.client(
            "ec2",
            region_name=connection.region,
        )

        az_response = ec2.describe_availability_zones()

        if not az_response.get("AvailabilityZones"):
            raise AwsConnectionError(
                f"Selected AWS region '{connection.region}' "
                "is unavailable or returned no availability zones."
            )

    except (ClientError, BotoCoreError) as exc:
        raise AwsConnectionError(
            f"Selected AWS region '{connection.region}' is unavailable.",
            technical=f"{exc.__class__.__name__}: {exc}",
        ) from exc

    # --- Validate that credentials can describe instances ---
    try:
        # AWS requires a value greater than 5 for this request.
        ec2.describe_instances(MaxResults=5)

    except (ClientError, BotoCoreError) as exc:
        code = str(
            (exc.response.get("Error") or {}).get("Code", "")
        )

        if code in (
            "AccessDenied",
            "AccessDeniedException",
        ):
            raise AwsConnectionError(
                "The CloudWise role is missing required deployment "
                "permissions. Update the permissions policy on your role "
                "and click Verify Again.",
                technical=f"{code}: {exc}",
            )

        raise AwsConnectionError(
            f"Cannot describe instances in region {connection.region}.",
            technical=f"{exc.__class__.__name__}: {exc}",
        ) from exc

    connection.status = "active"

    connection.save(
        update_fields=[
            "account_id",
            "status",
            "updated_at",
        ]
    )

    return connection


def get_active_connection(user) -> AWSConnection | None:
    return AWSConnection.objects.filter(
        user=user,
        status="active",
    ).first()


VERIFY_SCOPES = (
    "identity",
    "permissions",
    "region",
)


def verify(
    user,
    role_arn: str,
    region: str | None = None,
    scope: str = "identity",
) -> dict:
    """
    One phase of the beginner-facing verification checklist.

    Each scope is a single real AWS operation, so the UI can light up a
    check only when that check actually ran (no simulated progress):

      identity     — sts:AssumeRole + sts:GetCallerIdentity (role, account)
      permissions  — the Part 22 permission self-check (DryRun probes)
      region       — describe availability zones + read the EC2 inventory

    The connection stays ``pending`` until ``connect()`` succeeds, so a
    partial verification never claims the account is connected.
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

    connection.save(
        update_fields=[
            "role_arn",
            "region",
            "updated_at",
        ]
    )

    # ---------------------------------------------------------------
    # 1. Identity verification
    # ---------------------------------------------------------------
    if scope == "identity":
        session = get_session(connection)

        identity = session.client(
            "sts"
        ).get_caller_identity()

        account = str(
            identity.get("Account", "")
        )

        connection.account_id = account

        connection.save(
            update_fields=[
                "account_id",
                "updated_at",
            ]
        )

        return {
            "scope": "identity",
            "accountId": account,
            "roleArn": role_arn,
            "assumedRoleArn": str(
                identity.get("Arn", "")
            ),
            "externalId": connection.external_id,
            "region": connection.region,
        }

    # ---------------------------------------------------------------
    # 2. Permission verification
    # ---------------------------------------------------------------
    if scope == "permissions":
        from .preflight import (
            summarize,
            verify_permissions,
        )

        credentials = assume_role_credentials(
            connection
        )

        checks = verify_permissions(
            connection,
            credentials=credentials,
            region=connection.region,
        )

        ready, missing = summarize(
            checks
        )

        passed = sum(
            1
            for c in checks
            if c.get("ok") is True
        )

        return {
            "scope": "permissions",
            "checks": checks,
            "ready": ready,
            "missing": missing,
            "passed": passed,
            "total": len(checks),
            "region": connection.region,
        }

    # ---------------------------------------------------------------
    # 3. Region verification
    # ---------------------------------------------------------------
    if scope == "region":
        session = get_session(connection)

        ec2 = session.client(
            "ec2",
            region_name=connection.region,
        )

        try:
            zones = (
                ec2.describe_availability_zones()
                .get("AvailabilityZones")
                or []
            )

        except (ClientError, BotoCoreError) as exc:
            raise AwsConnectionError(
                f"AWS region '{connection.region}' is unavailable.",
                technical=f"{exc.__class__.__name__}: {exc}",
            ) from exc

        if not zones:
            raise AwsConnectionError(
                f"AWS region '{connection.region}' is unavailable."
            )

        try:
            # IMPORTANT:
            # Do not use MaxResults=1.
            # AWS rejects values <= 5 for this request.
            ec2.describe_instances(
                MaxResults=5
            )

        except (ClientError, BotoCoreError) as exc:
            code = str(
                (exc.response.get("Error") or {}).get("Code", "")
            )

            if code in (
                "AccessDenied",
                "AccessDeniedException",
            ):
                raise AwsConnectionError(
                    "The CloudWise role is missing required deployment "
                    "permissions. Update the permissions policy on your "
                    "role and click Verify Again.",
                    technical=f"{code}: {exc}",
                ) from exc

            raise AwsConnectionError(
                f"Cannot read EC2 in region {connection.region}.",
                technical=f"{exc.__class__.__name__}: {exc}",
            ) from exc

        return {
            "scope": "region",
            "region": connection.region,
            "availabilityZones": len(zones),
        }

    raise AwsConnectionError(
        f"Unknown verification step: {scope}"
    )


def connection_public_dict(
    connection: AWSConnection | None,
) -> dict:
    """Safe JSON view of a connection — contains no secrets by design."""

    if connection is None:
        return {
            "connected": False
        }

    return {
        "connected": connection.status == "active",
        "status": connection.status,
        "accountId": connection.account_id,
        "roleArn": connection.role_arn,
        "externalId": connection.external_id,
        "region": connection.region,
        "connectedAt": (
            connection.connected_at.isoformat()
            if connection.connected_at
            else None
        ),
    }


def disconnect(user) -> bool:
    """Remove the user's AWS connection (no cloud-side changes needed)."""

    deleted, _ = AWSConnection.objects.filter(
        user=user
    ).delete()

    return deleted > 0
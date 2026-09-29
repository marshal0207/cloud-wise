"""
Pre-deployment preflight and AWS permission self-check.

Part 21 — ``run_preflight`` answers, before anything is created, the only
question a beginner has: "will my deployment actually work?". Every check
is a real operation (never a guess) and every failure carries a remedy.

Part 22 — ``verify_permissions`` runs right after STS AssumeRole (both in
the preflight endpoint and inside the pipeline) and probes the AWS APIs
the pipeline is about to call, so a missing IAM action is reported as
"role X is missing permission Y" instead of failing 3 minutes later.

The canonical permission list lives in ``aws_permissions`` — the same
module that renders the policy the user pastes into IAM. Nothing here
hardcodes a second copy of that policy.
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from django.conf import settings

from .aws_permissions import get_cloudwise_permissions_policy
from .log_service import sanitize_message

logger = logging.getLogger(__name__)

# Errors that mean "explicitly denied" rather than "wrong arguments".
_DENIED_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "UnauthorizedOperation",
    "UnauthorizedAccess",
    "AuthFailure",
    "AuthorizationError",
    "ImplicitDeny",
    "ExplicitDeny",
    "InvalidClientTokenId",
}

# AMI parameter we read to resolve the image (must exist in the policy).
_AMI_PARAM = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"


def _error_code(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return str(exc.response.get("Error", {}).get("Code", "") or "")
    if isinstance(exc, NoCredentialsError):
        return "NoCredentialsError"
    return exc.__class__.__name__


def _error_message(exc: Exception) -> str:
    if isinstance(exc, ClientError):
        return str(
            (exc.response.get("Error") or {}).get("Message", "") or exc
        )
    return str(exc)


def _check(
    key: str,
    label: str,
    action: str,
    fn,
    *,
    critical: bool = True,
    remedy: str = "",
    optional: bool = False,
) -> dict:
    """
    Run one AWS probe and normalise the outcome.

    ``ok`` is True when the call succeeded, False when it was denied and
    None when the probe could not be evaluated (so it never blocks a
    deployment it cannot judge).

    ``optional`` marks a nice-to-have capability: even when the call is
    denied the check reports ``ok: None`` with ``critical: False`` so the
    deployment still proceeds on the fallback path.
    """
    try:
        detail = fn()
        return {
            "key": key,
            "label": label,
            "action": action,
            "ok": True,
            "critical": critical,
            "detail": sanitize_message(str(detail or "OK"))[:300],
            "remedy": remedy,
        }
    except Exception as exc:  # noqa: BLE001 — probe must never raise
        code = _error_code(exc)
        if code == "DryRunOperation":
            # DryRun succeeds precisely when the caller is allowed.
            return {
                "key": key,
                "label": label,
                "action": action,
                "ok": True,
                "critical": critical,
                "detail": "Permission confirmed (DryRun).",
                "remedy": remedy,
            }
        denied = code in _DENIED_CODES
        if optional and denied:
            return {
                "key": key,
                "label": label,
                "action": action,
                "ok": None,
                "critical": False,
                "code": code,
                "detail": sanitize_message(
                    f"{action} not available ({code}); continuing without "
                    "this optional capability."
                )[:300],
                "remedy": remedy,
            }
        return {
            "key": key,
            "label": label,
            "action": action,
            "ok": False if denied else None,
            "critical": critical and denied,
            "code": code,
            "detail": sanitize_message(f"{action}: {_error_message(exc)}")[:300],
            "remedy": remedy,
        }


def verify_permissions(connection, credentials: dict | None = None, region: str | None = None) -> list[dict]:
    """
    Probe every AWS API the deployment pipeline is about to use.

    Args:
        connection:   the user's AWSConnection (role ARN + external id).
        credentials:  optional temporary credentials. When omitted the
                      role is assumed here. A non-dict result (for
                      example a stub in the test suite) short-circuits
                      the probe so no network call is attempted.
        region:       overrides the connection's region.

    Returns:
        A list of check dicts: key, label, action, ok, critical, detail.
        ``ok`` may be None when the probe could not be evaluated.
    """
    if credentials is None:
        from .aws_connection_service import assume_role_credentials

        credentials = assume_role_credentials(connection)

    if not isinstance(credentials, dict) or not isinstance(
        credentials.get("aws_access_key_id"), str
    ):
        logger.info("Permission self-check skipped: no usable credentials.")
        return []

    target_region = region or getattr(connection, "region", None) or "ap-south-1"
    session = boto3.Session(
        aws_access_key_id=credentials.get("aws_access_key_id"),
        aws_secret_access_key=credentials.get("aws_secret_access_key"),
        aws_session_token=credentials.get("aws_session_token"),
        region_name=target_region,
    )

    checks: list[dict] = []

    # 1 — who did we just assume?
    def _identity() -> str:
        ident = session.client("sts").get_caller_identity()
        return f"Assumed {ident.get('Arn', '')} in account {ident.get('Account', '')}"

    checks.append(
        _check(
            "sts",
            "STS AssumeRole",
            "sts:GetCallerIdentity",
            _identity,
            remedy="Check the role trust policy and your External ID.",
        )
    )

    ec2 = session.client("ec2", region_name=target_region)

    def _az() -> str:
        zones = ec2.describe_availability_zones().get("AvailabilityZones") or []
        return f"Region {target_region} has {len(zones)} availability zone(s)"

    checks.append(
        _check(
            "region",
            "Region is available",
            "ec2:DescribeAvailabilityZones",
            _az,
            remedy=f"Pick a different region (currently {target_region}).",
        )
    )

    def _instances() -> str:
        ec2.describe_instances(MaxResults=5)
        return "EC2 instance inventory readable"

    checks.append(
        _check(
            "describe_instances",
            "Read EC2 instances",
            "ec2:DescribeInstances",
            _instances,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    def _vpcs() -> str:
        ec2.describe_vpcs()
        return "VPCs readable (security group setup possible)"

    checks.append(
        _check(
            "describe_vpcs",
            "Read VPC / networking",
            "ec2:DescribeVpcs",
            _vpcs,
            critical=False,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    # Optional: a stable public IP (Elastic IP) keeps the instance address
    # the same across rebuilds so a database network access list keeps
    # matching. Probed read-only; a denied role simply falls back to the
    # dynamic public IP, so this check must never block a deployment.
    if getattr(settings, "AWS_USE_ELASTIC_IP", True):

        def _elastic_ips() -> str:
            response = ec2.describe_addresses()
            count = len(response.get("Addresses") or [])
            return f"{count} Elastic IP address(es) visible"

        checks.append(
            _check(
                "elastic_ip",
                "Stable public IP (Elastic IP)",
                "ec2:DescribeAddresses",
                _elastic_ips,
                critical=False,
                optional=True,
                remedy=(
                    "Optional: add ec2:DescribeAddresses, ec2:AllocateAddress, "
                    "ec2:AssociateAddress, ec2:DisassociateAddress and "
                    "ec2:ReleaseAddress to your role to keep the public IP "
                    "stable across rebuilds (recommended for databases)."
                ),
            )
        )

    # 2 — resolve the AMI the pipeline will launch (also proves DescribeImages
    #      and the SSM public parameter read the policy grants).
    image_id = ""

    def _images() -> str:
        nonlocal image_id
        response = ec2.describe_images(
            Owners=["amazon"],
            Filters=[
                {"Name": "name", "Values": ["al2023-ami-*-x86_64"]},
                {"Name": "state", "Values": ["available"]},
            ],
        )
        images = sorted(
            response.get("Images", []), key=lambda i: i.get("CreationDate", ""), reverse=True
        )
        if not images:
            raise ClientError(
                {
                    "Error": {
                        "Code": "InvalidAMIID.NotFound",
                        "Message": "No Amazon Linux 2023 AMI found in this region.",
                    }
                },
                "DescribeImages",
            )
        image_id = images[0]["ImageId"]
        return f"Resolved deployment AMI {image_id}"

    checks.append(
        _check(
            "describe_images",
            "Find deployment AMI",
            "ec2:DescribeImages",
            _images,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    def _ami_parameter() -> str:
        ssm = session.client("ssm", region_name=target_region)
        value = ssm.get_parameter(Name=_AMI_PARAM)["Parameter"]["Value"]
        return f"SSM public AMI parameter readable ({value})"

    checks.append(
        _check(
            "ssm_parameter",
            "Read public AMI parameter",
            "ssm:GetParameter",
            _ami_parameter,
            critical=False,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    # 3 — launch permission, proven with DryRun (no instance is created).
    def _run_instances_dry_run() -> str:
        if not image_id:
            return "Skipped: no AMI available to test the launch with"
        ec2.run_instances(
            ImageId=image_id,
            InstanceType="t3.micro",
            MinCount=1,
            MaxCount=1,
            DryRun=True,
        )
        return "RunInstances allowed"

    checks.append(
        _check(
            "run_instances",
            "Launch EC2 instances (DryRun)",
            "ec2:RunInstances",
            _run_instances_dry_run,
            remedy=(
                "Attach the CloudWise permissions policy — the launch would "
                "fail without ec2:RunInstances and iam:PassRole."
            ),
        )
    )

    # 4 — SSM is how CloudWise uploads files and runs commands (no SSH).
    ssm = session.client("ssm", region_name=target_region)

    def _ssm_inventory() -> str:
        ssm.describe_instance_information(MaxResults=5)
        return "SSM managed-instance inventory readable"

    checks.append(
        _check(
            "ssm_describe",
            "AWS Systems Manager access",
            "ssm:DescribeInstanceInformation",
            _ssm_inventory,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    def _ssm_commands() -> str:
        ssm.list_commands(MaxResults=5)
        return "SSM command execution readable"

    checks.append(
        _check(
            "ssm_commands",
            "Run remote commands (no SSH needed)",
            "ssm:ListCommands",
            _ssm_commands,
            remedy="Attach the CloudWise permissions policy to your role.",
        )
    )

    return checks


def summarize(checks: list[dict]) -> tuple[bool, list[str]]:
    """Return (ready, missing_actions) for a permission check list."""
    missing: list[str] = []
    for check in checks:
        if check.get("ok") is False:
            missing.append(str(check.get("action") or check.get("key")))
        elif check.get("ok") is None and check.get("critical") and check.get("code") in _DENIED_CODES:
            missing.append(str(check.get("action") or check.get("key")))
    return (not missing), missing


def permission_policy_actions() -> list[str]:
    """Flattened action list from the canonical policy (single source)."""
    actions: list[str] = []
    for statement in get_cloudwise_permissions_policy():
        action = statement.get("Action")
        if isinstance(action, str):
            actions.append(action)
        elif isinstance(action, list):
            actions.extend(str(a) for a in action)
    return actions


def run_preflight(user, repo_name: str = "", include_repository: bool = False) -> dict:
    """
    Part 21 — everything CloudWise checks before a deployment may start.

    Returns a JSON-serialisable payload:
        {success, ready, accountId, region, checks: [...]}
    Every check has: key, label, ok, critical, detail, remedy.
    """
    from ...models import AWSConnection, GitHubConnection

    checks: list[dict] = []

    # --- GitHub ----------------------------------------------------
    github = GitHubConnection.objects.filter(user=user).first()
    github_ok = github is not None and github.status in ("connected", "expired")
    checks.append(
        {
            "key": "github",
            "label": "GitHub account connected",
            "ok": github_ok,
            "critical": True,
            "detail": (
                f"Authorized as {github.github_login}" if github_ok else "Not connected"
            ),
            "remedy": "Open Files & GitHub and authorize GitHub.",
        }
    )

    if include_repository and repo_name:
        if github_ok:
            try:
                from ..github_repository_service import inspect_repository

                inspect_repository(github.get_token(), repo_name)
                repo_ok, repo_detail = True, f"Repository {repo_name} is readable"
            except Exception as exc:  # noqa: BLE001 — surfaced as a failed check
                repo_ok, repo_detail = False, sanitize_message(str(exc))[:300]
        else:
            repo_ok, repo_detail = False, "GitHub is not connected"
        checks.append(
            {
                "key": "repository",
                "label": "Repository accessible",
                "ok": repo_ok,
                "critical": True,
                "detail": repo_detail,
                "remedy": "Re-authorize GitHub or check the repository name.",
            }
        )

    # --- AWS connection --------------------------------------------
    connection = AWSConnection.objects.filter(user=user, status="active").first()
    aws_ok = connection is not None
    checks.append(
        {
            "key": "aws_connection",
            "label": "AWS account connected (IAM role)",
            "ok": aws_ok,
            "critical": True,
            "detail": (
                f"Role {connection.role_arn} in account {connection.account_id}"
                if aws_ok
                else "No active AWS connection"
            ),
            "remedy": "Connect your AWS account on /connect-aws (no access keys).",
        }
    )

    account_id = connection.account_id if aws_ok else ""
    region = connection.region if aws_ok else ""

    if aws_ok:
        # --- STS + permission self-check (Part 22) -----------------
        from .aws_connection_service import AwsConnectionError, assume_role_credentials

        try:
            credentials = assume_role_credentials(connection)
        except AwsConnectionError as exc:
            credentials = None
            checks.append(
                {
                    "key": "assume_role",
                    "label": "STS AssumeRole",
                    "ok": False,
                    "critical": True,
                    "detail": sanitize_message(str(exc))[:300],
                    "remedy": (
                        "Verify the role trust policy matches your External ID "
                        "and allows CloudWise's account."
                    ),
                }
            )

        if credentials is not None:
            checks.append(
                {
                    "key": "assume_role",
                    "label": "STS AssumeRole",
                    "ok": True,
                    "critical": True,
                    "detail": f"Temporary credentials issued for {connection.role_arn}",
                    "remedy": "",
                }
            )
            permission_checks = verify_permissions(connection, credentials=credentials)
            checks.extend(permission_checks)

            for check in permission_checks:
                if check.get("ok") and not account_id and check.get("key") == "sts":
                    account_id = check.get("detail", "").split("account ")[-1].strip()

    ready = all(c.get("ok") is not False for c in checks if c.get("critical"))
    # Unverifiable (ok is None) critical checks do not block, but any
    # explicit denial does.
    return {
        "success": True,
        "ready": ready,
        "accountId": account_id,
        "region": region,
        "checks": checks,
    }

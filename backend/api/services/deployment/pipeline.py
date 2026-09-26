"""
End-to-end AWS deployment pipeline for a single DeploymentRecord.

Runs the real sequence inside the *user's* AWS account:

    validate IAM role (STS AssumeRole)
        → provision / reuse EC2
        → upload files + docker compose (or non-Docker runtime)
        → health check
        → live URL

Structured logs and status transitions are streamed into the
DeploymentRecord as they happen, so the frontend polls real state
instead of a timer.

By default the pipeline runs on a daemon thread so the HTTP request
returns immediately. Set ``DEPLOYMENT_RUN_INLINE = True`` (used by the
test suite) to run it synchronously in the request thread.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.utils import timezone

from ...models import AWSConnection, DeploymentRecord, Project
from .aws_connection_service import AwsConnectionError, assume_role_credentials
from .aws_ec2_provider import AwsEc2Error, AwsEc2Provider
from .status import DeploymentStage, DeploymentStatus

logger = logging.getLogger(__name__)


def _prepare_stage_status() -> dict[str, str]:
    """STS validation: the record stays in PREPARING."""
    return {
        DeploymentStage.PREPARING: DeploymentStatus.PREPARING,
        DeploymentStage.BUILDING: DeploymentStatus.PREPARING,
        DeploymentStage.DEPLOYING: DeploymentStatus.PREPARING,
        DeploymentStage.HEALTH_CHECK: DeploymentStatus.PREPARING,
        DeploymentStage.COMPLETED: DeploymentStatus.PREPARING,
        DeploymentStage.ROLLBACK: DeploymentStatus.PREPARING,
        DeploymentStage.FAILED: DeploymentStatus.FAILED,
    }


def _provision_stage_status() -> dict[str, str]:
    """EC2 capacity work: the record stays in BUILDING."""
    return {
        DeploymentStage.PREPARING: DeploymentStatus.BUILDING,
        DeploymentStage.BUILDING: DeploymentStatus.BUILDING,
        DeploymentStage.DEPLOYING: DeploymentStatus.BUILDING,
        DeploymentStage.HEALTH_CHECK: DeploymentStatus.BUILDING,
        DeploymentStage.COMPLETED: DeploymentStatus.BUILDING,
        DeploymentStage.ROLLBACK: DeploymentStatus.BUILDING,
        DeploymentStage.FAILED: DeploymentStatus.FAILED,
    }


def _deploy_stage_status() -> dict[str, str]:
    """Application deployment: mirrors the real provider state machine."""
    return {
        DeploymentStage.PREPARING: DeploymentStatus.DEPLOYING,
        DeploymentStage.BUILDING: DeploymentStatus.DEPLOYING,
        DeploymentStage.DEPLOYING: DeploymentStatus.DEPLOYING,
        DeploymentStage.HEALTH_CHECK: DeploymentStatus.HEALTH_CHECK,
        DeploymentStage.COMPLETED: DeploymentStatus.RUNNING,
        DeploymentStage.ROLLBACK: DeploymentStatus.ROLLING_BACK,
        DeploymentStage.FAILED: DeploymentStatus.FAILED,
    }


class RecordLogStream:
    """
    Callable that appends a structured log entry to a DeploymentRecord and,
    when the entry's stage maps to a deployment status in the current
    phase, advances ``deployment_status`` too.

    Only the pipeline thread writes, so read-modify-write is safe; the
    read endpoints use plain SELECTs.
    """

    def __init__(self, deployment_id: str, phase: str = "prepare"):
        self.deployment_id = deployment_id
        self.set_phase(phase)

    def set_phase(self, phase: str) -> None:
        self.phase = phase
        if phase == "provision":
            self.stage_status = _provision_stage_status()
        elif phase == "deploy":
            self.stage_status = _deploy_stage_status()
        else:
            self.stage_status = _prepare_stage_status()

    def __call__(self, entry: dict) -> None:
        record = DeploymentRecord.objects.filter(pk=self.deployment_id).first()
        if record is None:
            return
        logs = list(record.logs or [])
        logs.append(entry)
        values: dict = {"logs": logs, "updated_at": timezone.now()}
        new_status = self.stage_status.get(str(entry.get("stage") or ""))
        if new_status and new_status != record.deployment_status:
            values["deployment_status"] = new_status
        DeploymentRecord.objects.filter(pk=self.deployment_id).update(**values)


def append_log(
    deployment_id: str,
    level: str,
    stage: str,
    message: str,
) -> None:
    """Append one structured log entry (dedupes an identical trailing entry)."""
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        return
    logs = list(record.logs or [])
    if logs:
        last = logs[-1]
        if last.get("level") == level and last.get("message") == message:
            return
    from .log_service import make_log_entry

    logs.append(make_log_entry(stage, message, level=level))
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        logs=logs, updated_at=timezone.now()
    )


def fail_deployment(deployment_id: str, stage: str, message: str) -> None:
    """Record a terminal failure with an understandable, stage-tagged message."""
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        return
    logs = list(record.logs or [])
    from .log_service import make_log_entry

    if not (
        logs
        and logs[-1].get("level") == "ERROR"
        and logs[-1].get("message") == message
    ):
        logs.append(make_log_entry(stage, message, level="ERROR"))
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        logs=logs,
        deployment_status=DeploymentStatus.FAILED,
        updated_at=timezone.now(),
    )


def start_pipeline(deployment_id: str, payload: dict) -> None:
    """Run the pipeline inline (tests / explicit config) or on a thread."""
    if getattr(settings, "DEPLOYMENT_RUN_INLINE", False):
        run_pipeline(deployment_id, payload)
        return
    threading.Thread(
        target=run_pipeline,
        args=(deployment_id, payload),
        daemon=True,
        name=f"cloudwise-deploy-{deployment_id}",
    ).start()


def run_pipeline(deployment_id: str, payload: dict) -> None:
    """Execute the real AWS deployment for one DeploymentRecord."""
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        logger.warning("Deployment %s disappeared before the pipeline ran.", deployment_id)
        return

    stream = RecordLogStream(deployment_id, phase="prepare")

    # ------------------------------------------------------------------
    # Step 1 — validate the AWS connection (STS AssumeRole)
    # ------------------------------------------------------------------
    connection = None
    if record.aws_connection_id:
        connection = AWSConnection.objects.filter(
            pk=record.aws_connection_id, status="active"
        ).first()
    if connection is None and record.user_id:
        connection = AWSConnection.objects.filter(
            user_id=record.user_id, status="active"
        ).first()

    if connection is None:
        fail_deployment(
            deployment_id,
            DeploymentStage.PREPARING,
            "AWS: no active AWS connection for this account. "
            "Connect your AWS account (IAM role) and try again.",
        )
        return

    region = str(payload.get("region") or connection.region)
    append_log(
        deployment_id,
        "INFO",
        DeploymentStage.PREPARING,
        f"AWS: assuming IAM role via STS ({connection.role_arn}) "
        f"in {region}.",
    )
    try:
        assume_role_credentials(connection)
    except AwsConnectionError as exc:
        fail_deployment(deployment_id, DeploymentStage.PREPARING, f"AWS: {exc}")
        return

    aws_account_id = connection.account_id or ""
    values: dict = {"updated_at": timezone.now()}
    if aws_account_id:
        values["aws_account_id"] = aws_account_id
    if connection.region:
        values["region"] = connection.region
    DeploymentRecord.objects.filter(pk=deployment_id).update(**values)
    append_log(
        deployment_id,
        "INFO",
        DeploymentStage.PREPARING,
        f"AWS: account {aws_account_id or 'connected'} validated via "
        f"AssumeRole in {connection.region}.",
    )

    # ------------------------------------------------------------------
    # Step 2 — provision (or reuse) EC2 in the user's AWS account
    # ------------------------------------------------------------------
    provider = AwsEc2Provider(user=record.user, connection=connection)
    provider.set_log_listener(stream)

    stream.set_phase("provision")
    env_name = str(payload.get("environment_name") or record.environment_name)
    instance_type = payload.get("instance_type") or None
    append_log(
        deployment_id,
        "INFO",
        DeploymentStage.BUILDING,
        f"Provisioning EC2 capacity in {connection.region} "
        f"(instance type {instance_type or 'default'}, "
        f"environment {env_name}).",
    )
    try:
        provision_result = provider.start(
            {
                "environment_name": env_name,
                "provider": "AWS",
                "region": connection.region,
                "instance_type": instance_type,
                "force_new_instance": bool(payload.get("force_new_instance")),
                "specs": payload.get("specs") or {},
            }
        )
    except AwsEc2Error as exc:
        fail_deployment(deployment_id, DeploymentStage.BUILDING, f"EC2: {exc}")
        return

    instance_id = str(provision_result.get("instance_id") or "")
    public_ip = str(provision_result.get("public_ip") or "")
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        instance_id=instance_id,
        instance_type=str(provision_result.get("instance_type") or instance_type or ""),
        provider_deployment_id=instance_id,
        region=str(provision_result.get("region") or connection.region),
        aws_account_id=aws_account_id,
        ip_address=public_ip or None,
        updated_at=timezone.now(),
    )

    # ------------------------------------------------------------------
    # Step 3 — upload files, build, start containers, health check
    # ------------------------------------------------------------------
    stream.set_phase("deploy")
    append_log(
        deployment_id,
        "INFO",
        DeploymentStage.DEPLOYING,
        f"Deploying application to instance {instance_id} "
        f"({len(payload.get('files') or {})} file(s)).",
    )
    try:
        deploy_result = provider.deploy(
            {
                "instance_id": instance_id,
                "deployment_id": instance_id,
                "files": payload.get("files") or {},
                "env_vars": payload.get("env_vars") or {},
                "project_id": str(payload.get("project_id") or "default"),
                "environment_name": env_name,
                "port": payload.get("port"),
                "region": connection.region,
                "detection": payload.get("detection") or {},
                "deployment_plan": payload.get("deployment_plan") or {},
            }
        )
    except AwsEc2Error as exc:
        fail_deployment(deployment_id, DeploymentStage.DEPLOYING, f"Deploy: {exc}")
        return
    except Exception as exc:  # noqa: BLE001 — never leave a record stuck
        logger.exception("Unexpected deployment failure for %s", deployment_id)
        fail_deployment(deployment_id, DeploymentStage.DEPLOYING, f"Deploy: {exc}")
        return

    live_url = str(deploy_result.get("endpoint_url") or "")
    endpoint_ip = str(deploy_result.get("public_ip") or public_ip or "")
    final_status = (
        deploy_result.get("status")
        if deploy_result.get("status") in DeploymentStatus.ALL
        else DeploymentStatus.RUNNING
    )
    specs = dict(record.specs or {})
    specs.update(
        {
            "instanceId": instance_id,
            "instanceType": provision_result.get("instance_type") or instance_type or "",
            "reused": provision_result.get("reused", False),
            "securityGroupId": provision_result.get("security_group_id"),
            "amiId": provision_result.get("ami_id"),
            "appPort": payload.get("port"),
        }
    )
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        deployment_status=final_status,
        live_url=live_url or None,
        ip_address=endpoint_ip or public_ip or None,
        instance_id=instance_id,
        instance_type=specs.get("instanceType", ""),
        specs=specs,
        updated_at=timezone.now(),
    )
    append_log(
        deployment_id,
        "INFO",
        DeploymentStage.COMPLETED,
        (
            f"Deployment {final_status}: application live at {live_url}."
            if live_url
            else f"Deployment {final_status} on instance {instance_id}."
        ),
    )

    _persist_to_project(deployment_id)


def _persist_to_project(deployment_id: str) -> None:
    """Mirror the outcome onto the owning project so the UI can show it."""
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None or record.project_id is None:
        return
    project = Project.objects.filter(pk=record.project_id).first()
    if project is None:
        return
    project.deployment = {
        **(project.deployment or {}),
        "provider": record.provider,
        "awsInstanceId": record.instance_id,
        "provider_deployment_id": record.instance_id,
        "status": record.deployment_status,
        "ipAddress": record.ip_address,
        "endpointUrl": record.live_url,
        "repository": record.repository,
    }
    project.save(update_fields=["deployment"])

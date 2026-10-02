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

Lifecycle rule: this pipeline never stops or terminates EC2. A
successful run ends at ``RUNNING`` with the instance left running, and
the record stays RUNNING until the user explicitly stops
(``POST /deployments/<id>/stop``) or destroys
(``POST /deployments/<id>/terminate``) the deployment.
"""

from __future__ import annotations

import logging
import threading

from django.conf import settings
from django.utils import timezone

from ...models import AWSConnection, DeploymentRecord, Project
from .aws_connection_service import AwsConnectionError, assume_role_credentials
from .aws_ec2_provider import AwsEc2Error, AwsEc2Provider
from .lifecycle import deployment_worker
from .log_service import make_log_entry, sanitize_message
from .status import (
    DeploymentStage,
    DeploymentStatus,
    is_valid_transition,
    progress_for,
)

logger = logging.getLogger(__name__)

# Statuses that end a deployment run (no further pipeline work).
_TERMINAL_STATUSES = (
    DeploymentStatus.RUNNING,
    DeploymentStatus.FAILED,
    DeploymentStatus.ROLLED_BACK,
    DeploymentStatus.TERMINATED,
)

# The happy path in order. Used to walk a deployment forward when a
# status jump would otherwise be illegal (for example a mocked provider
# that reports RUNNING straight from DEPLOYING).
_LADDER: tuple[str, ...] = (
    DeploymentStatus.QUEUED,
    DeploymentStatus.PREPARING,
    DeploymentStatus.BUILDING,
    DeploymentStatus.DEPLOYING,
    DeploymentStatus.HEALTH_CHECK,
    DeploymentStatus.RUNNING,
)


def resolve_transition(current: str, target: str) -> list[str] | None:
    """
    Return the statuses to walk through to reach ``target`` from
    ``current``, or None when the change is not permitted at all.
    """
    if current == target:
        return [target]
    if is_valid_transition(current, target):
        return [target]
    if current in _LADDER and target in _LADDER:
        start, end = _LADDER.index(current), _LADDER.index(target)
        if end > start:
            return list(_LADDER[start + 1 : end + 1])
    return None


def _status_fields(
    record: DeploymentRecord,
    to_status: str,
    message: str,
    stage: str | None = None,
    error_code: str = "",
    error_message: str = "",
) -> dict:
    """
    Field changes implied by moving ``record`` to ``to_status``.

    Part 11: status, stage, progress, message, timestamps and error
    details always move together, so the UI never sees a status without
    the stage/progress that explains it.
    """
    now = timezone.now()
    fields: dict = {
        "deployment_status": to_status,
        "progress": progress_for(to_status),
        "status_message": sanitize_message(message or "")[:500],
        "updated_at": now,
    }
    if stage:
        fields["current_stage"] = stage
    if record.started_at is None and to_status != DeploymentStatus.QUEUED:
        fields["started_at"] = now
    if to_status in _TERMINAL_STATUSES:
        fields["finished_at"] = now
    if to_status == DeploymentStatus.FAILED:
        fields["error_code"] = error_code or record.error_code or "DEPLOYMENT_FAILED"
        fields["error_message"] = (error_message or message or "")[:1000]
    elif to_status in (DeploymentStatus.QUEUED, DeploymentStatus.RUNNING):
        fields["error_code"] = ""
        fields["error_message"] = ""
    return fields


def set_status(
    deployment_id: str,
    to_status: str,
    stage: str | None = None,
    message: str = "",
    level: str = "INFO",
    error_code: str = "",
    error_message: str = "",
    append_entry: bool = True,
) -> bool:
    """
    Move a deployment to ``to_status`` through the state machine.

    Returns True when the transition was applied. An illegal transition
    (for example writing FAILED onto a deployment the user already
    stopped) is refused and logged instead of being forced.
    """
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        return False

    # ------------------------------------------------------------------
    # Lifecycle safety: a background worker may never destroy a healthy
    # deployment. RUNNING -> TERMINATED is only reachable after an
    # explicit stop (cancel_requested is set by POST
    # /deployments/<id>/stop) or an explicit destroy. A stale cleanup,
    # finally block or late worker write is logged as an error and
    # refused instead of being applied.
    # ------------------------------------------------------------------
    if (
        record.deployment_status != to_status
        and record.deployment_status == DeploymentStatus.RUNNING
        and to_status == DeploymentStatus.TERMINATED
        and not record.cancel_requested
    ):
        logger.error(
            "Refused automatic deployment %s transition RUNNING -> "
            "TERMINATED (%s): no explicit stop/destroy was requested. "
            "A successful deployment keeps its EC2 instance running.",
            deployment_id,
            message,
        )
        return False

    # A stopped deployment is frozen: the pipeline winding down after an
    # explicit stop must not move it to TERMINATED/FAILED or re-run it.
    if (
        record.deployment_status != to_status
        and record.deployment_status == DeploymentStatus.STOPPED
    ):
        logger.warning(
            "Refused deployment %s transition STOPPED -> %s: %s",
            deployment_id,
            to_status,
            message,
        )
        return False

    values: dict = {"updated_at": timezone.now()}
    if append_entry:
        entry = make_log_entry(
            stage or record.current_stage or DeploymentStage.PREPARING,
            message,
            level=level,  # type: ignore[arg-type]
        )
        values["logs"] = list(record.logs or []) + [entry]

    if record.deployment_status != to_status:
        path = resolve_transition(record.deployment_status, to_status)
        if path is None:
            logger.warning(
                "Refused deployment %s transition %s → %s: %s",
                deployment_id,
                record.deployment_status,
                to_status,
                message,
            )
            # A stopped deployment is frozen: no further status or log
            # writes from a pipeline that is winding down.
            if record.deployment_status != DeploymentStatus.TERMINATED:
                DeploymentRecord.objects.filter(pk=deployment_id).update(**values)
            return False
        values.update(_status_fields(record, to_status, message, stage, error_code, error_message))
    else:
        if stage:
            values["current_stage"] = stage
        if message:
            values["status_message"] = sanitize_message(message)[:500]

    DeploymentRecord.objects.filter(pk=deployment_id).update(**values)
    return True


def stop_requested(deployment_id: str) -> bool:
    """True when the user asked to stop this deployment (Part 14)."""
    from django.db.models import Q

    return DeploymentRecord.objects.filter(pk=deployment_id).filter(
        Q(cancel_requested=True)
        | Q(deployment_status=DeploymentStatus.TERMINATED)
    ).exists()


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
        if record.deployment_status in (
            DeploymentStatus.TERMINATED,
            DeploymentStatus.STOPPED,
        ):
            # Frozen by a user stop — a winding-down pipeline must not
            # keep appending progress to a stopped deployment.
            return
        safe_entry = dict(entry)
        safe_entry["message"] = sanitize_message(str(entry.get("message") or ""))
        logs = list(record.logs or [])
        logs.append(safe_entry)
        values: dict = {"logs": logs, "updated_at": timezone.now()}

        stage = str(safe_entry.get("stage") or "")
        if stage:
            values["current_stage"] = stage
        values["status_message"] = safe_entry["message"][:500]

        hint = self.stage_status.get(stage)
        if hint and hint != record.deployment_status:
            if resolve_transition(record.deployment_status, hint) is not None:
                values.update(
                    _status_fields(
                        record,
                        hint,
                        safe_entry["message"],
                        stage,
                    )
                )
                values["logs"] = logs  # _status_fields never touches logs
            else:
                logger.warning(
                    "Deployment %s stage %s wanted %s from %s — ignored.",
                    self.deployment_id,
                    stage,
                    hint,
                    record.deployment_status,
                )
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
    if record.deployment_status in (
        DeploymentStatus.TERMINATED,
        DeploymentStatus.STOPPED,
    ):
        return
    message = sanitize_message(message)
    logs = list(record.logs or [])
    if logs:
        last = logs[-1]
        if last.get("level") == level and last.get("message") == message:
            return

    logs.append(make_log_entry(stage, message, level=level))
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        logs=logs,
        status_message=message[:500],
        updated_at=timezone.now(),
    )


def fail_deployment(
    deployment_id: str,
    stage: str,
    message: str,
    error_code: str = "",
) -> None:
    """
    Record a terminal failure with an understandable, stage-tagged message.

    A deployment the user already stopped (TERMINATED or STOPPED) is
    never overwritten with FAILED — the stop wins (Part 14).
    """
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        return
    message = sanitize_message(message)
    logs = list(record.logs or [])
    if not (
        logs
        and logs[-1].get("level") == "ERROR"
        and logs[-1].get("message") == message
    ):
        logs.append(make_log_entry(stage, message, level="ERROR"))

    if record.deployment_status in (
        DeploymentStatus.TERMINATED,
        DeploymentStatus.STOPPED,
    ):
        # An explicitly stopped deployment is frozen: the failure log is
        # kept for diagnostics, but the status is never overwritten.
        DeploymentRecord.objects.filter(pk=deployment_id).update(
            logs=logs, updated_at=timezone.now()
        )
        return

    values = dict(
        _status_fields(
            record,
            DeploymentStatus.FAILED,
            message,
            stage,
            error_code=error_code or f"FAILED_{stage}",
            error_message=message,
        )
    )
    values["logs"] = logs  # _status_fields never touches logs
    if not is_valid_transition(record.deployment_status, DeploymentStatus.FAILED):
        for key in (
            "deployment_status",
            "progress",
            "error_code",
            "error_message",
            "finished_at",
            "started_at",
        ):
            values.pop(key, None)
    DeploymentRecord.objects.filter(pk=deployment_id).update(**values)


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
    """
    Execute the real AWS deployment for one DeploymentRecord.

    The whole run executes inside the deployment-worker marker: the
    provider refuses EC2 TerminateInstances issued from this background
    worker, so no cleanup/finally handler added here can ever destroy a
    successfully deployed instance. Termination stays an explicit user
    action (POST /deployments/<id>/terminate).
    """
    with deployment_worker():
        _run_pipeline(deployment_id, payload)


def _run_pipeline(deployment_id: str, payload: dict) -> None:
    record = DeploymentRecord.objects.filter(pk=deployment_id).first()
    if record is None:
        logger.warning("Deployment %s disappeared before the pipeline ran.", deployment_id)
        return

    # Part 11: the run always starts on the state machine's first edge.
    if stop_requested(deployment_id):
        set_status(
            deployment_id,
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.PREPARING,
            message="Deployment was stopped before the pipeline started.",
        )
        return
    set_status(
        deployment_id,
        DeploymentStatus.PREPARING,
        stage=DeploymentStage.PREPARING,
        message=(
            f"Preparing deployment of {record.repository or 'the repository'} "
            f"to AWS ({payload.get('region') or record.region})."
        ),
    )

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
            error_code="AWS_NOT_CONNECTED",
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
        credentials = assume_role_credentials(connection)
    except AwsConnectionError as exc:
        fail_deployment(
            deployment_id,
            DeploymentStage.PREPARING,
            f"AWS: {exc}",
            error_code="STS_ASSUME_ROLE_FAILED",
        )
        return

    # ------------------------------------------------------------------
    # Step 1b — permission self-check (Part 22)
    #
    # Probes the exact APIs this pipeline is about to call, so a role
    # missing ec2:RunInstances / ssm:SendCommand fails here with the
    # missing action named instead of minutes later.
    # ------------------------------------------------------------------
    from .preflight import summarize, verify_permissions

    try:
        permission_checks = verify_permissions(
            connection, credentials=credentials, region=region
        )
    except Exception as exc:  # noqa: BLE001 — a self-check never breaks a deploy
        logger.warning("Permission self-check failed to run for %s: %s", deployment_id, exc)
        permission_checks = []

    if permission_checks:
        for check in permission_checks:
            level = "INFO" if check.get("ok") else "WARNING"
            if check.get("ok") is None:
                level = "INFO"
            append_log(
                deployment_id,
                level,
                DeploymentStage.PREPARING,
                f"Permission check [{check.get('action')}] "
                f"{check.get('label')}: "
                f"{'OK' if check.get('ok') else check.get('detail')}",
            )
        ready, missing = summarize(permission_checks)
        if not ready:
            fail_deployment(
                deployment_id,
                DeploymentStage.PREPARING,
                "AWS: your CloudWiseDeployRole is missing permission(s): "
                + ", ".join(missing)
                + ". Attach the CloudWise permissions policy to the role "
                "and retry.",
                error_code="AWS_PERMISSION_DENIED",
            )
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
        f"AssumeRole in {connection.region}. "
        f"Permission self-check passed for {len(permission_checks)} API(s).",
    )

    if stop_requested(deployment_id):
        set_status(
            deployment_id,
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.PREPARING,
            message="Deployment stopped by user before provisioning.",
        )
        return

    # ------------------------------------------------------------------
    # Step 2 — provision (or reuse) EC2 in the user's AWS account
    # ------------------------------------------------------------------
    provider = AwsEc2Provider(user=record.user, connection=connection)
    provider.set_log_listener(stream)

    stream.set_phase("provision")
    env_name = str(payload.get("environment_name") or record.environment_name)
    instance_type = payload.get("instance_type") or None
    set_status(
        deployment_id,
        DeploymentStatus.BUILDING,
        stage=DeploymentStage.BUILDING,
        message=(
            f"Provisioning EC2 capacity in {connection.region} "
            f"(instance type {instance_type or 'default'}, "
            f"environment {env_name})."
        ),
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
        fail_deployment(
            deployment_id,
            DeploymentStage.BUILDING,
            f"EC2: {exc}",
            error_code="EC2_PROVISION_FAILED",
        )
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

    if stop_requested(deployment_id):
        set_status(
            deployment_id,
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.DEPLOYING,
            message=(
                f"Deployment stopped by user after instance {instance_id} "
                "was provisioned."
            ),
        )
        return

    # ------------------------------------------------------------------
    # Step 3 — upload files, build, start containers, health check
    # ------------------------------------------------------------------
    stream.set_phase("deploy")
    files = payload.get("files") or {}
    set_status(
        deployment_id,
        DeploymentStatus.DEPLOYING,
        stage=DeploymentStage.DEPLOYING,
        message=(
            f"Deploying application to instance {instance_id} "
            f"({len(files)} file(s), {len(payload.get('env_vars') or {})} "
            "environment variable(s))."
        ),
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
        fail_deployment(
            deployment_id,
            DeploymentStage.DEPLOYING,
            f"Deploy: {exc}",
            # A specific diagnosis from the provider (database / backend /
            # nginx / frontend) wins over the generic deploy failure code.
            error_code=getattr(exc, "error_code", "") or "DEPLOY_FAILED",
        )
        return
    except Exception as exc:  # noqa: BLE001 — never leave a record stuck
        logger.exception("Unexpected deployment failure for %s", deployment_id)
        fail_deployment(
            deployment_id,
            DeploymentStage.DEPLOYING,
            f"Deploy: {exc}",
            error_code="DEPLOY_UNEXPECTED_ERROR",
        )
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
    # Split-architecture live verification report (additive key — only set
    # for separate frontend/ + backend/ deployments).
    health_report = deploy_result.get("health")
    if isinstance(health_report, dict):
        specs["health"] = health_report
    # Real endpoint + database facts from the provider (never fabricated:
    # every value below comes from a probe that actually answered).
    for key, spec_key in (
        ("frontend_url", "frontendUrl"),
        ("backend_health_url", "backendHealthUrl"),
        ("elastic_ip", "elasticIp"),
        ("public_ip", "publicIp"),
    ):
        value = deploy_result.get(key)
        if isinstance(value, str) and value:
            specs[spec_key] = value
    database_report = deploy_result.get("database")
    if isinstance(database_report, dict) and database_report:
        specs["database"] = database_report
    DeploymentRecord.objects.filter(pk=deployment_id).update(
        live_url=live_url or None,
        ip_address=endpoint_ip or public_ip or None,
        instance_id=instance_id,
        instance_type=specs.get("instanceType", ""),
        specs=specs,
        updated_at=timezone.now(),
    )

    database_status = str(
        (database_report or {}).get("status") if isinstance(database_report, dict) else ""
    )
    final_message = (
        f"Deployment {final_status}: application live at {live_url}."
        + (f" Database: {database_status}." if database_status else "")
        if live_url
        else f"Deployment {final_status} on instance {instance_id}."
    )
    # A stop that landed while the containers were starting wins: the
    # record stays TERMINATED and is never flipped back to RUNNING.
    if stop_requested(deployment_id):
        set_status(
            deployment_id,
            DeploymentStatus.TERMINATED,
            stage=DeploymentStage.COMPLETED,
            message=(
                f"Deployment stopped by user. Instance {instance_id} is "
                "managed separately (stop it from the deployment page)."
            ),
        )
        _persist_to_project(deployment_id)
        return

    set_status(
        deployment_id,
        final_status,
        stage=(
            DeploymentStage.COMPLETED
            if final_status == DeploymentStatus.RUNNING
            else DeploymentStage.FAILED
        ),
        message=final_message,
        level="INFO" if final_status == DeploymentStatus.RUNNING else "ERROR",
        error_code="" if final_status == DeploymentStatus.RUNNING else "DEPLOY_FAILED",
        error_message="" if final_status == DeploymentStatus.RUNNING else final_message,
    )

    if final_status == DeploymentStatus.RUNNING and instance_id:
        # The pipeline ends here. EC2 keeps running until the user
        # explicitly stops or destroys the deployment.
        append_log(
            deployment_id,
            "INFO",
            DeploymentStage.COMPLETED,
            f"Deployment {deployment_id} completed successfully; "
            f"keeping EC2 {instance_id} running.",
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

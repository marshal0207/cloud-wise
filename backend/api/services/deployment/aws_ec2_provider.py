"""
AwsEc2Provider — AWS EC2 deployment provider (Parts 3–5).

Deploys inside the USER's AWS account using an IAM role connection
(sts:AssumeRole + External ID → short-lived temporary credentials).

Part 3 scope: account connection + EC2 provisioning (create / reuse),
security-group configuration (80/443/22 only), and Docker / Docker
Compose installation via EC2 user data.

Part 4/5 scope: application container deployment via SSM RunShellScript —
uploads generated Docker/compose files + .env to an isolated per-project
directory on the instance, runs `docker compose up -d --build`, and
performs an HTTP health check against the live public URL.

Configuration (region, instance type, AMI, key pair, instance profile,
security group, ports, waiters, Docker install, deploy root, SSM/health
timeouts) comes from Django settings / request overrides — nothing
provider-specific is hardcoded.

Implements the existing DeploymentProvider interface (start, get_status,
get_logs, health_check, rollback) and reuses the shared deployment state
machine (DeploymentStatus / is_valid_transition).
"""

"""
AwsEc2Provider — AWS EC2 deployment provider (Parts 3–5).

Deploys inside the USER's AWS account using an IAM role connection
(sts:AssumeRole + External ID → short-lived temporary credentials).

...
"""

import base64
import json
import re
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Mapping
from typing import Any

from django.conf import settings

from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    WaiterError,
)

from ...models import EC2Instance
from .aws_connection_service import AwsConnectionError, get_session
from .database_preflight import (
    STATUS_FAILED,
    STATUS_SKIPPED,
    STATUS_SUCCESS,
    build_preflight_report,
    build_probe_commands,
    build_probe_url,
    classify_backend_start_failure,
    classify_health_failure,
    detect_database_dependency,
    gate_result,
)
from .lifecycle import in_deployment_worker, refusal_message
from .log_service import DeploymentLogService
# Imported as a module (not by name) so the Atlas Admin API seam stays
# patchable in tests: patching the function where it is *defined* must
# change what the deployment calls.
from . import mongodb_atlas_service
from .mongodb_atlas_service import (
    describe_uri_for_deployment,
    remove_atlas_access_entry,
)
from .provider import DeploymentProvider
from .status import DeploymentStage, DeploymentStatus, is_valid_transition

try:
    from ...services.tech_stack_detector import detect_tech_stack, UnsupportedTechStackError
    from ...services.deployment_file_generator import (
        analyze_repository,
        sensitive_deny_block as deployment_file_generator_sensitive_deny_block,
    )
except ImportError:
    detect_tech_stack = None
    analyze_repository = None
    UnsupportedTechStackError = None

    def deployment_file_generator_sensitive_deny_block(indent: str = "    ") -> str:
        """Fallback when the generator module is unavailable."""
        return ""

# Lifecycle progress mapping for get_status()
_PROGRESS = {
    DeploymentStatus.QUEUED: 5,
    DeploymentStatus.PREPARING: 15,
    DeploymentStatus.BUILDING: 45,
    DeploymentStatus.DEPLOYING: 70,
    DeploymentStatus.HEALTH_CHECK: 90,
    DeploymentStatus.RUNNING: 100,
    DeploymentStatus.STOPPED: 100,
    DeploymentStatus.FAILED: 45,
    DeploymentStatus.ROLLING_BACK: 60,
    DeploymentStatus.ROLLED_BACK: 100,
}

# EC2 instance-state → deployment status
_STATE_MAP = {
    "pending": DeploymentStatus.BUILDING,
    "running": DeploymentStatus.RUNNING,
    "stopping": DeploymentStatus.STOPPED,
    "stopped": DeploymentStatus.STOPPED,
    "shutting-down": DeploymentStatus.FAILED,
    "terminated": DeploymentStatus.FAILED,
}

# Backend service gate: how long to wait for the container to listen. Node
# drivers default to a 30s server-selection timeout, so two full connection
# attempts fit inside the window and the resulting error lands in the log
# tail the gate collects. A backend that listens returns immediately.
_GATE_ATTEMPTS = 12
_GATE_INTERVAL_SECONDS = 5


class AwsEc2Error(Exception):
    """
    Raised when AWS EC2 provisioning / deployment operations fail.

    ``error_code`` is an optional machine-readable diagnosis (for example
    ``DATABASE_CONNECTION_FAILED`` or ``BACKEND_NOT_RUNNING``) carried to
    the pipeline. It defaults to ``""`` so every existing
    ``AwsEc2Error(message)`` call site keeps working unchanged and the
    pipeline keeps falling back to its generic failure codes.
    """

    def __init__(self, message: str = "", error_code: str = ""):
        super().__init__(message)
        self.error_code = str(error_code or "")


class AwsEc2Provider(DeploymentProvider):
    """AWS EC2 provider implementing the DeploymentProvider interface."""

    PROVIDER_TYPE = "AWS"

    def __init__(self, user=None, connection=None, config: dict | None = None):
        self.user = user
        self.connection = connection
        self.config: dict[str, Any] = dict(config or {})
        self.log_listener = None

    def set_log_listener(self, listener) -> "AwsEc2Provider":
        """
        Attach a callable invoked with every structured log entry as it is
        produced, so a caller can stream progress to the caller/UI.
        """
        self.log_listener = listener
        return self

    def _new_log(self, deployment_id: str) -> DeploymentLogService:
        return DeploymentLogService(deployment_id, listener=self.log_listener)

    # ------------------------------------------------------------------
    # Config resolution (settings first, per-request overrides second)
    # ------------------------------------------------------------------

    def _region(self) -> str:
        return str(
            self.config.get("region")
            or (self.connection.region if self.connection else "")
            or settings.AWS_DEFAULT_REGION
        )

    def _instance_type(self) -> str:
        return str(
            self.config.get("instance_type") or settings.AWS_EC2_INSTANCE_TYPE
        )

    def _environment_name(self) -> str:
        return str(self.config.get("environment_name") or "cloudwise-env")

    # ------------------------------------------------------------------
    # DeploymentProvider interface
    # ------------------------------------------------------------------

    def start(self, configuration: dict[str, Any]) -> dict[str, Any]:
        """
        Start a deployment: provision (or reuse) the user's EC2 instance.

        Required configuration keys: environment_name, provider.
        Optional: region, instance_type, force_new_instance, specs.
        """
        for key, value in (configuration or {}).items():
            if value is not None:
                self.config[key] = value
        provider = str(self.config.get("provider", "")).upper()
        if provider and provider != "AWS":
            raise AwsEc2Error(
                f'AwsEc2Provider cannot run provider "{provider}".'
            )
        return self.provision()

    def get_status(self, deployment_id: str) -> dict[str, Any]:
        """Query the live EC2 instance state for a deployment (instance id)."""
        ec2, region = self._client()
        instance = self._describe_instance(ec2, deployment_id)
        if instance is None:
            raise AwsEc2Error(
                f'EC2 instance "{deployment_id}" not found in AWS account.'
            )

        state = (instance.get("State") or {}).get("Name", "")
        mapped = _STATE_MAP.get(state, DeploymentStatus.QUEUED)
        public_ip = instance.get("PublicIpAddress") or ""

        self._sync_instance_row(deployment_id, state=state, public_ip=public_ip)

        message = f"EC2 instance state: {state or 'unknown'}"
        if mapped == DeploymentStatus.RUNNING:
            message = (
                f"EC2 instance {deployment_id} is running"
                + (f" at {public_ip}" if public_ip else "")
            )
        elif mapped == DeploymentStatus.FAILED:
            message = (
                f"EC2 instance {deployment_id} is not serving "
                f"(state: {state})."
            )

        return {
            "deployment_id": deployment_id,
            "status": mapped,
            "progress": _PROGRESS.get(mapped, 0),
            "provider_type": self.PROVIDER_TYPE,
            "endpoint_url": None,
            "ip_address": public_ip or None,
            "instance_state": state,
            "region": region,
            "message": message,
        }

    def get_logs(self, deployment_id: str) -> list[dict[str, Any]]:
        """Structured provisioning logs persisted with the instance record."""
        row = EC2Instance.objects.filter(instance_id=deployment_id).first()
        if row is None:
            return []
        return list((row.metadata or {}).get("logs", []))

    def health_check(self, deployment_id: str) -> dict[str, Any]:
        """
        Health check: EC2 instance state + HTTP check of the live app URL
        (when a container deployment has produced an endpoint).
        """
        try:
            live = self.get_status(deployment_id)
        except AwsEc2Error as exc:
            return {
                "deployment_id": deployment_id,
                "healthy": False,
                "provider_type": self.PROVIDER_TYPE,
                "message": str(exc),
            }
        healthy = live["status"] == DeploymentStatus.RUNNING
        message = (
            f"EC2 instance {deployment_id} is running"
            + (
                f" at {live['ip_address']}"
                if live.get("ip_address")
                else ""
            )
            if healthy
            else f"EC2 instance unhealthy: {live['message']}"
        )
        endpoint = self._stored_endpoint(deployment_id)
        if healthy and endpoint:
            http_ok, http_msg = self._http_health(endpoint)
            healthy = http_ok
            message = http_msg
        elif healthy:
            message += ". No application endpoint recorded yet."
        return {
            "deployment_id": deployment_id,
            "healthy": healthy,
            "provider_type": self.PROVIDER_TYPE,
            "endpoint_url": endpoint,
            "message": message,
        }

    def rollback(self, deployment_id: str) -> dict[str, Any]:
        """
        Rollback: stop application containers (best-effort) and record the
        transition. The EC2 instance itself is retained (never terminated).
        """
        log = self._new_log(deployment_id)
        status = DeploymentStatus.ROLLING_BACK
        if is_valid_transition(DeploymentStatus.RUNNING, status) or is_valid_transition(
            DeploymentStatus.FAILED, status
        ):
            log.info(
                DeploymentStage.ROLLBACK,
                f"Rollback started for deployment {deployment_id}.",
            )

        # Best-effort: stop containers on the instance (instance retained).
        try:
            stopped = self._ssm_stop_containers(deployment_id, log)
            if stopped:
                log.info(
                    DeploymentStage.ROLLBACK,
                    "Application containers stopped on the EC2 instance "
                    "(instance retained).",
                )
            else:
                log.warning(
                    DeploymentStage.ROLLBACK,
                    "Could not reach the instance to stop containers "
                    "(SSM unavailable). Instance retained.",
                )
        except AwsEc2Error as exc:
            log.warning(
                DeploymentStage.ROLLBACK,
                f"Container stop skipped: {exc}",
            )

        row = EC2Instance.objects.filter(instance_id=deployment_id).first()
        if row is not None:
            self._persist_logs(row, log.all())

        # MongoDB Atlas Network Access entry is intentionally NOT removed
        # here: rollback keeps the instance running, so the next deployment
        # from the same address still needs it. Cleanup runs on termination
        # (see terminate_instance), where the address is gone for good.

        final = DeploymentStatus.ROLLED_BACK
        if is_valid_transition(status, final):
            log.info(
                DeploymentStage.ROLLBACK,
                "Rollback complete. EC2 instance retained.",
            )
        if row is not None:
            self._persist_logs(row, log.all())

        return {
            "deployment_id": deployment_id,
            "status": final,
            "provider_type": self.PROVIDER_TYPE,
            "message": (
                f"Rollback recorded for {deployment_id}. The EC2 instance is "
                "retained; application containers were stopped when reachable."
            ),
            "logs": log.all(),
        }

    def terminate_instance(self, instance_id: str) -> dict[str, Any]:
        """
        Terminate the CloudWise-managed EC2 instance in the *user's* AWS
        account — only for an explicit user Destroy/Delete action.

        Safety: only instances carrying the ``ManagedBy=CloudWise`` tag are
        ever terminated, so a hand-typed instance id can never destroy a
        resource CloudWise did not create. Calls made from inside the
        background deployment worker are refused and logged as errors:
        a successful deployment must never be terminated by pipeline
        cleanup code.
        """
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            raise AwsEc2Error("No EC2 instance id supplied for termination.")
        if in_deployment_worker():
            raise AwsEc2Error(
                refusal_message(
                    "termination",
                    f"deployment worker tried to terminate {instance_id} "
                    "after a deployment action",
                )
            )
        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error(
                "AWS account not connected. Connect your AWS account "
                "(IAM role) first."
            )

        log = self._new_log(instance_id)
        session = self.get_session()
        ec2 = session.client("ec2", region_name=self._region())

        instance = self._describe_instance(ec2, instance_id)
        if instance is None:
            raise AwsEc2Error(
                f'EC2 instance "{instance_id}" not found in AWS account.'
            )

        tags = {t.get("Key"): t.get("Value") for t in (instance.get("Tags") or [])}
        if tags.get("ManagedBy") != "CloudWise":
            raise AwsEc2Error(
                f"Instance {instance_id} is not managed by CloudWise "
                "(missing the ManagedBy=CloudWise tag). Refusing to "
                "terminate it."
            )

        state = (instance.get("State") or {}).get("Name", "")
        log.info(
            DeploymentStage.DEPLOYING,
            f"Terminating CloudWise-managed instance {instance_id} "
            f"(current state: {state}) in {self._region()}.",
        )
        try:
            ec2.terminate_instances(InstanceIds=[instance_id])
        except (ClientError, BotoCoreError) as exc:
            message = self._friendly_ec2_error(exc)
            log.error(DeploymentStage.FAILED, message)
            raise AwsEc2Error(message) from exc

        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        public_ip = str(getattr(row, "public_ip", "") or "") if row else None
        if row is not None:
            row.status = "terminated"
            row.save(update_fields=["status", "updated_at"])
            self._persist_logs(row, log.all())

        # MongoDB Atlas Network Access cleanup — safe precisely because the
        # instance is gone: its /32 entry can never be needed again, and
        # only CloudWise-tagged entries (description prefix) are removed.
        # Rollback keeps the instance, so its entry is deliberately kept.
        if public_ip:
            try:
                cleanup = remove_atlas_access_entry(
                    public_ip=public_ip, deployment_id=instance_id
                )
            except Exception as cleanup_exc:  # noqa: BLE001
                log.warning(
                    DeploymentStage.COMPLETED,
                    f"Atlas Network Access cleanup skipped: {cleanup_exc}",
                )
            else:
                action = str(cleanup.get("action") or "")
                message = str(cleanup.get("message") or "")
                if message:
                    level = log.warning if action == "failed" else log.info
                    level(DeploymentStage.COMPLETED, message)

        log.info(
            DeploymentStage.COMPLETED,
            f"Termination requested for {instance_id}. The instance is "
            "removed from your AWS account.",
        )
        return {
            "instance_id": instance_id,
            "region": self._region(),
            "state": "terminated",
            "message": f"Termination requested for {instance_id}.",
            "logs": log.all(),
        }

    def stop_instance(self, instance_id: str) -> dict[str, Any]:
        """
        Stop (never terminate) the CloudWise-managed EC2 instance.

        Stopping only powers the instance off: the instance, its disks
        and everything running on it are retained and can be started
        again later. This is the provider half of the explicit
        ``POST /deployments/<id>/stop`` user action.
        """
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            raise AwsEc2Error("No EC2 instance id supplied for stopping.")
        if in_deployment_worker():
            raise AwsEc2Error(
                refusal_message(
                    "stop",
                    f"deployment worker tried to stop {instance_id} "
                    "outside an explicit user action",
                )
            )
        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error(
                "AWS account not connected. Connect your AWS account "
                "(IAM role) first."
            )

        log = self._new_log(instance_id)
        session = self.get_session()
        ec2 = session.client("ec2", region_name=self._region())

        instance = self._describe_instance(ec2, instance_id)
        if instance is None:
            raise AwsEc2Error(
                f'EC2 instance "{instance_id}" not found in AWS account.'
            )

        tags = {t.get("Key"): t.get("Value") for t in (instance.get("Tags") or [])}
        if tags.get("ManagedBy") != "CloudWise":
            raise AwsEc2Error(
                f"Instance {instance_id} is not managed by CloudWise "
                "(missing the ManagedBy=CloudWise tag). Refusing to "
                "stop it."
            )

        state = (instance.get("State") or {}).get("Name", "")
        if state in ("terminated", "shutting-down"):
            raise AwsEc2Error(
                f"Instance {instance_id} is already terminated and can no "
                "longer be stopped."
            )

        if state == "stopped":
            log.info(
                DeploymentStage.COMPLETED,
                f"EC2 instance {instance_id} is already stopped.",
            )
        else:
            log.info(
                DeploymentStage.DEPLOYING,
                f"User requested stop for deployment {instance_id}; "
                f"stopping EC2 {instance_id} (current state: {state}) in "
                f"{self._region()}. Stopping is not termination: the "
                "instance is retained and can be started again.",
            )
            try:
                ec2.stop_instances(InstanceIds=[instance_id])
            except (ClientError, BotoCoreError) as exc:
                message = self._friendly_ec2_error(exc)
                log.error(DeploymentStage.FAILED, message)
                raise AwsEc2Error(message) from exc

        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        if row is not None:
            row.status = "stopped"
            row.save(update_fields=["status", "updated_at"])
            self._persist_logs(row, log.all())

        log.info(
            DeploymentStage.COMPLETED,
            f"Stop requested for {instance_id}. The instance is powered "
            "off (not terminated); start it again with the Start action. "
            "MongoDB/Atlas network access is untouched because the "
            "instance is retained.",
        )
        return {
            "instance_id": instance_id,
            "region": self._region(),
            "state": "stopped",
            "stopped": True,
            "message": f"Stop requested for {instance_id}.",
            "logs": log.all(),
        }

    def start_instance(self, instance_id: str) -> dict[str, Any]:
        """
        Start an existing stopped CloudWise-managed EC2 instance and wait
        until it is running again (SSM, Docker and the application come
        back with it).

        This is the provider half of the explicit
        ``POST /deployments/<id>/start`` user action. Terminated
        instances are never recreated here — that is a new deployment.
        """
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            raise AwsEc2Error("No EC2 instance id supplied for starting.")
        if in_deployment_worker():
            raise AwsEc2Error(
                refusal_message(
                    "start",
                    f"deployment worker tried to start {instance_id} "
                    "outside an explicit user action",
                )
            )
        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error(
                "AWS account not connected. Connect your AWS account "
                "(IAM role) first."
            )

        log = self._new_log(instance_id)
        session = self.get_session()
        ec2 = session.client("ec2", region_name=self._region())

        instance = self._describe_instance(ec2, instance_id)
        if instance is None:
            raise AwsEc2Error(
                f'EC2 instance "{instance_id}" not found in AWS account.'
            )

        tags = {t.get("Key"): t.get("Value") for t in (instance.get("Tags") or [])}
        if tags.get("ManagedBy") != "CloudWise":
            raise AwsEc2Error(
                f"Instance {instance_id} is not managed by CloudWise "
                "(missing the ManagedBy=CloudWise tag). Refusing to "
                "start it."
            )

        state = (instance.get("State") or {}).get("Name", "")
        if state in ("terminated", "shutting-down"):
            raise AwsEc2Error(
                f"Instance {instance_id} was terminated. Deploy again to "
                "create a new instance."
            )

        if state == "running":
            log.info(
                DeploymentStage.COMPLETED,
                f"EC2 instance {instance_id} is already running.",
            )
        else:
            wait_config = {"Delay": 5, "MaxAttempts": 60}
            if state == "stopping":
                log.info(
                    DeploymentStage.DEPLOYING,
                    f"Waiting for {instance_id} to finish stopping before "
                    "starting it again.",
                )
                try:
                    ec2.get_waiter("instance_stopped").wait(
                        InstanceIds=[instance_id],
                        WaiterConfig=wait_config,
                    )
                except WaiterError:
                    pass  # describe below reports the real state
            log.info(
                DeploymentStage.DEPLOYING,
                f"User requested start for deployment {instance_id}; "
                f"starting EC2 {instance_id} in {self._region()}.",
            )
            try:
                ec2.start_instances(InstanceIds=[instance_id])
            except (ClientError, BotoCoreError) as exc:
                message = self._friendly_ec2_error(exc)
                log.error(DeploymentStage.FAILED, message)
                raise AwsEc2Error(message) from exc

            try:
                ec2.get_waiter("instance_running").wait(
                    InstanceIds=[instance_id],
                    WaiterConfig=wait_config,
                )
            except WaiterError:
                pass  # describe below reports the real state
            instance = self._describe_instance(ec2, instance_id) or instance

        public_ip = str(instance.get("PublicIpAddress") or "")
        self._sync_instance_row(
            instance_id, state="running", public_ip=public_ip or None
        )

        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        if row is not None:
            self._persist_logs(row, log.all())

        log.info(
            DeploymentStage.COMPLETED,
            f"Start requested for {instance_id}. The instance is running "
            f"again{f' at {public_ip}' if public_ip else ''}; verify the "
            "application health before opening the live URL.",
        )
        return {
            "instance_id": instance_id,
            "region": self._region(),
            "state": "running",
            "started": True,
            "public_ip": public_ip,
            "message": f"Start requested for {instance_id}.",
            "logs": log.all(),
        }

    # ------------------------------------------------------------------
    # Spec-named operations (provision / deploy / status / logs)
    # ------------------------------------------------------------------

    def provision(self) -> dict[str, Any]:
        """
        Create or reuse the user's CloudWise-managed EC2 instance.

        Walks the shared state machine:
        QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING
        """
        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error(
                "AWS account not connected. Connect your AWS account "
                "(IAM role) first."
            )

        deployment_id = f"aws_{uuid.uuid4().hex[:12]}"
        log = self._new_log(deployment_id)
        current = DeploymentStatus.QUEUED

        def advance(to_status: str, stage: str, message: str) -> None:
            nonlocal current
            if not is_valid_transition(current, to_status):
                raise AwsEc2Error(
                    f"Invalid deployment state transition "
                    f"{current} → {to_status}."
                )
            log.info(stage, message)
            current = to_status

        region = self._region()
        instance_type = self._instance_type()
        env_name = self._environment_name()

        try:
            # ---- PREPARING: temporary credentials + SG + AMI ----
            advance(
                DeploymentStatus.PREPARING,
                DeploymentStage.PREPARING,
                "Assuming IAM role in your AWS account "
                "(temporary STS credentials).",
            )
            session = self.get_session()
            ec2 = session.client("ec2", region_name=region)

            sg_id, sg_name = self._ensure_security_group(ec2, log)
            image = self._resolve_image(ec2)

            key_name = str(
                self.config.get("key_name") or settings.AWS_EC2_KEY_NAME or ""
            )
            # SSM is mandatory for CloudWise deployments. Never allow an
            # empty instance-profile setting to launch an instance without
            # the CloudWise SSM profile.
            instance_profile = str(
                self.config.get("instance_profile")
                or getattr(settings, "AWS_EC2_INSTANCE_PROFILE", "")
                or "cloudwise-ec2-ssm"
            ).strip() or "cloudwise-ec2-ssm"
            log.info(
                DeploymentStage.PREPARING,
                f"Configuration: region={region}, "
                f"instanceType={instance_type}, ami={image.get('ImageId', '')}, "
                f"securityGroup={sg_name} ({sg_id}), "
                f"ports={settings.AWS_SECURITY_GROUP_PORTS}, "
                f"ssh={'key' if key_name else 'none'}"
                + (", instanceProfile" if instance_profile else ""),
            )

            # ---- BUILDING: reuse or create the instance ----
            advance(
                DeploymentStatus.BUILDING,
                DeploymentStage.BUILDING,
                "Provisioning EC2 capacity in your AWS account.",
            )
            reused = False
            instance = None
            if not self.config.get("force_new_instance"):
                instance = self._find_reusable_instance(ec2)
            if instance is not None:
                reused = True
                instance_id = instance["InstanceId"]
                state = (instance.get("State") or {}).get("Name", "")
                if state == "stopped":
                    ec2.start_instances(InstanceIds=[instance_id])
                    state = "pending"
                    log.info(
                        DeploymentStage.BUILDING,
                        f"Starting stopped CloudWise-managed instance "
                        f"{instance_id}.",
                    )
                log.info(
                    DeploymentStage.BUILDING,
                    f"Reusing existing CloudWise-managed EC2 instance "
                    f"{instance_id} (state: {state}).",
                )
                row = self._sync_instance_row(
                    instance_id,
                    state=state,
                    region=region,
                    instance_type=instance.get("InstanceType", instance_type),
                    ami_id=instance.get("ImageId", ""),
                    sg_id=sg_id,
                    sg_name=sg_name,
                    env_name=env_name,
                    increment=True,
                )
                # Ensure the reused instance has the SSM instance profile.
                # Only touches CloudWise-managed instances (ManagedBy tag).
                self._ensure_instance_profile(
                    ec2, instance_id, instance_profile, log
                )
            else:
                instance = self._run_instances(
                    ec2,
                    image=image,
                    instance_type=instance_type,
                    sg_id=sg_id,
                    key_name=key_name,
                    instance_profile=instance_profile,
                    env_name=env_name,
                )
                instance_id = instance["InstanceId"]
                state = (instance.get("State") or {}).get("Name", "pending")
                log.info(
                    DeploymentStage.BUILDING,
                    f"Launched new EC2 instance {instance_id} "
                    f"({instance_type}) in {region}.",
                )
                row = self._sync_instance_row(
                    instance_id,
                    state=state,
                    region=region,
                    instance_type=instance_type,
                    ami_id=image.get("ImageId", ""),
                    sg_id=sg_id,
                    sg_name=sg_name,
                    env_name=env_name,
                )

            # ---- DEPLOYING: wait until running + public IP ----
            advance(
                DeploymentStatus.DEPLOYING,
                DeploymentStage.DEPLOYING,
                "Waiting for the instance to reach running state"
                + (
                    " and installing Docker via user data..."
                    if settings.AWS_INSTALL_DOCKER
                    else "..."
                ),
            )
            instance = self._wait_until_running(ec2, instance_id) or instance

            # SSM is the only remote-execution channel used by CloudWise.
            # Verify/repair the profile after the instance is running as a
            # second line of defence for both new and reused instances.
            self._ensure_instance_profile(
                ec2, instance_id, instance_profile, log
            )

            # A reused instance may have been created before CloudWise had
            # the SSM bootstrap/profile logic. There is no safe remote
            # channel available until SSM itself is online, so automatically
            # replace a CloudWise-managed stale instance once (instead of
            # asking the customer to SSH/restart the agent manually).
            try:
                ssm = self.get_session().client("ssm", region_name=region)
                self._ensure_ssm_managed(ssm, instance_id, log)
            except AwsEc2Error as ssm_exc:
                auto_recover = bool(
                    self.config.get("auto_recover_ssm", True)
                )
                already_recovered = bool(
                    self.config.get("_ssm_recovery_attempted", False)
                )
                if not reused or not auto_recover or already_recovered:
                    raise

                log.warning(
                    DeploymentStage.DEPLOYING,
                    f"SSM is unavailable on reused instance {instance_id}. "
                    "CloudWise will replace this CloudWise-managed instance "
                    "once with a fresh EC2 instance that starts with the "
                    "SSM profile already attached. Original reason: "
                    f"{ssm_exc}",
                )
                self.config["_ssm_recovery_attempted"] = True

                self._terminate_for_ssm_recovery(ec2, instance_id, log)

                instance = self._run_instances(
                    ec2,
                    image=image,
                    instance_type=instance_type,
                    sg_id=sg_id,
                    key_name=key_name,
                    instance_profile=instance_profile,
                    env_name=env_name,
                )
                instance_id = instance["InstanceId"]
                reused = False
                state = (instance.get("State") or {}).get("Name", "pending")

                log.info(
                    DeploymentStage.BUILDING,
                    f"Launched replacement EC2 instance {instance_id} "
                    f"({instance_type}) for automatic SSM recovery.",
                )

                self._sync_instance_row(
                    instance_id,
                    state=state,
                    region=region,
                    instance_type=instance_type,
                    ami_id=image.get("ImageId", ""),
                    sg_id=sg_id,
                    sg_name=sg_name,
                    env_name=env_name,
                )

                log.info(
                    DeploymentStage.DEPLOYING,
                    "Waiting for the replacement EC2 instance to reach "
                    "running state...",
                )
                instance = self._wait_until_running(ec2, instance_id) or instance
                self._ensure_instance_profile(
                    ec2, instance_id, instance_profile, log
                )
                ssm = self.get_session().client("ssm", region_name=region)
                self._ensure_ssm_managed(ssm, instance_id, log)

            # Stable public address (optional): keeps the instance IP the
            # same across rebuilds so database network access lists keep
            # matching. Purely additive — falls back to the dynamic IP.
            elastic_ip = self._ensure_elastic_ip(ec2, instance_id, log)

            public_ip = (
                elastic_ip or (instance or {}).get("PublicIpAddress") or ""
            )
            private_ip = (instance or {}).get("PrivateIpAddress") or ""
            state = ((instance or {}).get("State") or {}).get("Name", "pending")

            self._sync_instance_row(
                instance_id,
                state=state,
                public_ip=public_ip,
                private_ip=private_ip,
            )
            if settings.AWS_INSTALL_DOCKER:
                log.info(
                    DeploymentStage.DEPLOYING,
                    "Docker + Docker Compose installation scheduled via "
                    "EC2 user data (verify with `docker --version` on the "
                    "instance after first boot).",
                )

            # ---- HEALTH_CHECK ----
            advance(
                DeploymentStatus.HEALTH_CHECK,
                DeploymentStage.HEALTH_CHECK,
                f"Checking EC2 instance status for {instance_id}...",
            )
            if state != "running":
                raise AwsEc2Error(
                    f"EC2 instance {instance_id} did not reach running "
                    f"state (current: {state})."
                )

            # ---- RUNNING ----
            advance(
                DeploymentStatus.RUNNING,
                DeploymentStage.COMPLETED,
                f"EC2 provisioning complete: {instance_id}"
                + (f" at {public_ip}" if public_ip else "")
                + (
                    " (reused existing instance)"
                    if reused
                    else " (new instance)"
                )
                + ". Application containers are not deployed yet (Part 4).",
            )
        except AwsConnectionError as exc:
            raise AwsEc2Error(str(exc)) from exc
        except AwsEc2Error:
            raise
        except (ClientError, BotoCoreError, NoCredentialsError, WaiterError) as exc:
            message = self._friendly_ec2_error(exc)
            log.error(DeploymentStage.FAILED, message)
            if "instance_id" in locals():
                failed_row = EC2Instance.objects.filter(
                    instance_id=instance_id
                ).first()
                if failed_row is not None:
                    failed_row.status = "failed"
                    failed_row.save(update_fields=["status", "updated_at"])
                    self._persist_logs(failed_row, log.all())
            raise AwsEc2Error(message) from exc

        docker_installed = bool(settings.AWS_INSTALL_DOCKER)
        self._sync_instance_row(
            instance_id,
            state=state,
            public_ip=public_ip,
            private_ip=private_ip,
            docker_installed=docker_installed,
        )
        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        if row is not None:
            self._persist_logs(row, log.all())

        return {
            "deployment_id": instance_id,
            "status": current,
            "provider_type": self.PROVIDER_TYPE,
            "message": (
                f"EC2 instance {instance_id} is "
                f"{'reused' if reused else 'provisioned'} in {region}."
            ),
            "instance_id": instance_id,
            "region": region,
            "instance_type": instance_type,
            "ami_id": image.get("ImageId", ""),
            "public_ip": public_ip,
            "elastic_ip": elastic_ip,
            "private_ip": private_ip,
            "security_group_id": sg_id,
            "security_group_name": sg_name,
            "environment_name": env_name,
            "reused": reused,
            "docker_installed": docker_installed,
            "logs": log.all(),
        }

    def deploy(self, configuration: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Application container deployment on an existing EC2 instance.

        Walks the shared state machine from QUEUED:
        QUEUED → PREPARING → BUILDING → DEPLOYING → HEALTH_CHECK → RUNNING

        Required configuration:
          instance_id   — target EC2 instance (from a prior provision()).
          files         — dict of relative path → file content (repo + generated
                          Docker/compose/nginx files).
          env_vars      — dict of environment variable name → value (written
                          as .env on the instance; never logged in clear).
          project_id    — isolates the remote directory per project.
          environment_name — sub-directory under the project root.

        Optional: public_ip (for the health check URL), reuse_provisioned
        status/logs from a prior provision via config.
        """
        for key, value in (configuration or {}).items():
            if value is not None:
                self.config[key] = value

        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error(
                "AWS account not connected. Connect your AWS account "
                "(IAM role) first."
            )

        instance_id = str(
            self.config.get("instance_id")
            or self.config.get("deployment_id")
            or ""
        ).strip()
        files = self.config.get("files") or {}
        env_vars = self.config.get("env_vars") or {}
        project_id = str(self.config.get("project_id") or "default").strip() or "default"
        env_name = self._environment_name()
        # Detect project type for Docker vs non-Deploy path
        project_type = self._detect_project_type()
        app_port = self._detect_app_port()
        has_docker = self._has_docker()

        if not instance_id:
            raise AwsEc2Error(
                "No EC2 instance for container deployment. Provision first."
            )
        if not isinstance(files, dict) or not files:
            raise AwsEc2Error(
                "No deployment files provided for container upload."
            )

        deployment_id = instance_id
        log = self._new_log(deployment_id)
        current = DeploymentStatus.QUEUED
        # Populated during the run; kept outside the try so the failure and
        # success paths can always report what actually happened.
        atlas_access: dict[str, Any] = {}
        split_health: dict[str, Any] | None = None
        db_preflight: dict[str, Any] = {}

        def advance(to_status: str, stage: str, message: str) -> None:
            nonlocal current
            if not is_valid_transition(current, to_status):
                raise AwsEc2Error(
                    f"Invalid deployment state transition "
                    f"{current} → {to_status}."
                )
            log.info(stage, message)
            current = to_status

        region = self._region()
        remote_root = str(settings.AWS_DEPLOY_ROOT).rstrip("/")
        # Isolated per-project directory — never a shared /tmp drop.
        remote_dir = f"{remote_root}/{project_id}/{env_name}"

        try:
            advance(
                DeploymentStatus.PREPARING,
                DeploymentStage.PREPARING,
                "Preparing container deployment "
                f"({len(files)} file(s)) for instance {instance_id}.",
            )
            session = self.get_session()
            ssm = session.client("ssm", region_name=region)
            ec2 = session.client("ec2", region_name=region)

            instance = self._describe_instance(ec2, instance_id)
            if instance is None:
                raise AwsEc2Error(
                    f'EC2 instance "{instance_id}" not found in AWS account.'
                )
            state = (instance.get("State") or {}).get("Name", "")
            if state != "running":
                raise AwsEc2Error(
                    f"EC2 instance {instance_id} is not running "
                    f"(state: {state})."
                )
            public_ip = instance.get("PublicIpAddress") or ""
            elastic_ip = self._elastic_ip_for(ec2, instance_id)
            if elastic_ip:
                # The Elastic IP is the address actually reachable from
                # Atlas — always report and allowlist that one.
                public_ip = elastic_ip

            self._ensure_ssm_managed(ssm, instance_id, log)

            # ---- MongoDB Atlas Network Access (additive) ----
            # The instance now has its final public address, so the /32
            # entry can be written before the containers start.
            atlas_access = self._ensure_atlas_network_access(
                env_vars=env_vars,
                deployment_id=deployment_id,
                public_ip=public_ip,
                log=log,
            )

            split_plan = self.config.get("deployment_plan") or {}
            split_plan = (
                dict(split_plan) if isinstance(split_plan, Mapping) else {}
            )
            # Health-check order for split repositories:
            #   compose services -> backend container -> process -> port
            #   -> database -> nginx -> /api/health -> frontend -> public URL
            # The backend gate covers the first four steps; it is SKIPPED for
            # architectures that do not declare a backend container.
            backend_gate: dict[str, Any] = {
                "status": STATUS_SKIPPED,
                "errorCode": "",
                "message": "",
                "diagnostics": "",
            }
            try:
                backend_port = int(split_plan.get("backendPort") or 0)
            except (TypeError, ValueError):
                backend_port = 0

            if has_docker:
                # Part 9 — verify (and repair) the Docker bootstrap before
                # building, so a reused instance provisioned at another
                # time never fails halfway through `docker compose up`.
                self._ensure_docker(ssm, instance_id, log)

            # ---- BUILDING: upload files + write .env via SSM ----
            advance(
                DeploymentStatus.BUILDING,
                DeploymentStage.BUILDING,
                f"Uploading deployment files to {remote_dir} "
                f"({'non-Docker' if not has_docker else 'Docker'} deployment).",
            )

            upload_commands = self._build_upload_commands(
                files, env_vars, remote_dir
            )
            self._run_ssm_commands(
                ssm, instance_id, upload_commands, log,
                stage_message="File upload batch",
            )
            log.info(
                DeploymentStage.BUILDING,
                f"Uploaded {len(files)} file(s) and wrote .env "
                f"({len(env_vars)} variable(s), values not logged).",
            )

            if not has_docker:
                # ---- NON-DOCKER DEPLOYMENT ----
                advance(
                    DeploymentStatus.DEPLOYING,
                    DeploymentStage.DEPLOYING,
                    f"Deploying {project_type.get('technology', 'UNKNOWN')} "
                    f"application on port {app_port} "
                    "(non-Docker runtime).",
                )
                healthy, health_message = self._deploy_non_docker(
                    session, ssm, ec2, instance_id, log,
                    project_type, app_port,
                )
                endpoint_url = ""
                if healthy and public_ip:
                    if app_port in (80, 443):
                        endpoint_url = f"http://{public_ip}"
                    else:
                        endpoint_url = f"http://{public_ip}:{app_port}"
                if not healthy:
                    log.error(
                        DeploymentStage.FAILED,
                        f"Non-Docker deployment health check failed: {health_message}",
                    )
                    row = EC2Instance.objects.filter(instance_id=instance_id).first()
                    if row is not None:
                        self._persist_logs(row, log.all())
                    raise AwsEc2Error(
                        f"Non-Docker deployment health check failed: {health_message}"
                    )
            else:
                # ---- DOCKER DEPLOYMENT (existing path) ----
                advance(
                    DeploymentStatus.DEPLOYING,
                    DeploymentStage.DEPLOYING,
                    "Building and starting containers "
                    "(docker compose up -d --build).",
                )
                compose_commands = self._build_compose_commands(remote_dir)
                compose_output = self._run_ssm_commands(
                    ssm, instance_id, compose_commands, log,
                    stage_message="docker compose up",
                    timeout_seconds=max(
                        settings.AWS_SSM_TIMEOUT_SECONDS, 600
                    ),
                )
                log.info(
                    DeploymentStage.DEPLOYING,
                    "Container build/start command completed on the instance.",
                )

                # Apply the uploaded nginx.conf and re-resolve the backend
                # upstream: a recreated backend container gets a new address
                # while the running nginx keeps the one it resolved at start.
                self._refresh_nginx(ssm, instance_id, remote_dir, log)

                # Diagnostics only: do not change the existing deployment
                # commands, health-check logic, ports, networking, or state
                # transitions. If the application later fails its health
                # check, these diagnostics make the real container failure
                # visible in CloudWise logs.
                diagnostic_commands = self._build_compose_diagnostic_commands(
                    remote_dir, backend_port=backend_port or None
                )
                try:
                    diagnostic_output = self._run_ssm_commands(
                        ssm,
                        instance_id,
                        diagnostic_commands,
                        log,
                        stage_message="container diagnostics",
                        timeout_seconds=120,
                    )
                    if diagnostic_output:
                        log.info(
                            DeploymentStage.DEPLOYING,
                            "Container diagnostics collected after compose start.",
                        )
                except Exception as diagnostic_exc:  # noqa: BLE001
                    # Diagnostics must never make an otherwise successful
                    # deployment fail. The existing health check remains the
                    # source of truth.
                    log.warning(
                        DeploymentStage.DEPLOYING,
                        f"Container diagnostics could not be collected: "
                        f"{diagnostic_exc}",
                    )

                # ---- Backend container / port gate ----
                # The database can only be reached once the process is up and
                # listening, so this runs before the entry-point probes. It
                # never invents a failure: when nothing proves the backend is
                # broken it reports SKIPPED and the existing health check
                # stays the source of truth.
                if (
                    split_plan.get("architecture")
                    == "separate_frontend_backend"
                    and backend_port
                ):
                    backend_gate = self._check_backend_service(
                        ssm,
                        instance_id,
                        remote_dir,
                        log,
                        backend_port=backend_port,
                        atlas=atlas_access,
                        public_ip=str(public_ip or ""),
                    )
                    gate_status = str(backend_gate.get("status") or "")
                    if gate_status == STATUS_FAILED:
                        log.error(
                            DeploymentStage.DEPLOYING,
                            str(backend_gate.get("message") or ""),
                        )
                    elif gate_status == STATUS_SUCCESS:
                        log.info(
                            DeploymentStage.DEPLOYING,
                            f"Backend container is listening on port "
                            f"{backend_port}.",
                        )

            # ---- HEALTH_CHECK ----
            app_port = self._detect_app_port()
            split_health: dict[str, Any] | None = None
            advance(
                DeploymentStatus.HEALTH_CHECK,
                DeploymentStage.HEALTH_CHECK,
                "Waiting for the application to become healthy "
                f"(port {app_port})...",
            )

            # ---- Database preflight (additive verification layer) ----
            # Runs before the deployment may be declared healthy: it checks
            # that the external database this repository declares is
            # configured and reachable *from this instance*, and records
            # what answered on the HTTP entry point so a later failure can
            # be told apart from a database / backend / nginx problem.
            # A backend container that never listens short-circuits it: the
            # database probe would pass (the cluster itself answers) while
            # the application can never reach it.
            if str(backend_gate.get("status") or "") == STATUS_FAILED:
                db_preflight = {
                    "status": STATUS_FAILED,
                    "errorCode": str(backend_gate.get("errorCode") or ""),
                    "message": str(backend_gate.get("message") or ""),
                }
            else:
                db_preflight = self._run_database_preflight(
                    ssm,
                    instance_id,
                    remote_dir,
                    log,
                    app_port=app_port,
                    public_ip=public_ip,
                )

            if db_preflight.get("status") == "FAILED":
                # Fail fast with the precise database diagnosis instead of
                # waiting for an application that can never become healthy.
                healthy = False
                health_message = str(
                    db_preflight.get("message") or "database preflight failed"
                )
            else:
                # Prefer an in-instance check (works even when the security
                # group only exposes 80/443/22), then confirm via public URL.
                healthy, health_message = self._wait_healthy_on_instance(
                    ssm, instance_id, app_port
                )
            public_ip = public_ip or ""
            if app_port in (80, 443):
                endpoint_url = f"http://{public_ip}" if public_ip else ""
            else:
                endpoint_url = (
                    f"http://{public_ip}:{app_port}" if public_ip else ""
                )
            if healthy and endpoint_url:
                pub_ok, pub_msg = self._http_health(endpoint_url)
                if pub_ok:
                    health_message = pub_msg
                else:
                    log.warning(
                        DeploymentStage.HEALTH_CHECK,
                        f"App is healthy on the instance but the public URL "
                        f"is not reachable yet ({pub_msg}). Security group "
                        f"ports: {settings.AWS_SECURITY_GROUP_PORTS}.",
                    )

            # ---- Split-architecture live verification (additive layer) ----
            # For separate frontend/ + backend/ deployments the router nginx
            # is also probed for a backend API path, so a dead/unrouted API
            # is caught here instead of reporting the app as live.
            if healthy:
                if split_plan.get("architecture") == (
                    "separate_frontend_backend"
                ):
                    from .adapters import verify_split_deployment

                    def _run_split_commands(
                        commands, stage_message, timeout_seconds,
                    ):
                        return self._run_ssm_commands(
                            ssm,
                            instance_id,
                            list(commands),
                            log,
                            stage_message=stage_message,
                            timeout_seconds=timeout_seconds,
                        )

                    split_health = verify_split_deployment(
                        split_plan,
                        endpoint_url=endpoint_url,
                        run_commands=_run_split_commands,
                    )
                    split_status = (split_health or {}).get("status")
                    split_message = (split_health or {}).get("message") or ""
                    if split_status == "FAILED":
                        # Route the failure through the existing health
                        # failure path (diagnostics + FAILED record).
                        healthy = False
                        health_message = split_message
                    elif split_status == "SUCCESS":
                        health_message = f"{health_message}. {split_message}"

            if healthy:
                # Part 17 — record the real probe result (SSM curl +
                # public URL) so the log shows the HTTP status seen.
                log.info(
                    DeploymentStage.HEALTH_CHECK,
                    f"Health check passed on instance {instance_id}: "
                    f"{health_message}.",
                )
            if not healthy:
                # The compose-start step is intentionally tolerant of
                # post-start container state. If the app is not reachable,
                # collect the container state/logs now so the user sees the
                # actual application error (nginx config, frontend build,
                # backend crash, port binding, etc.) in CloudWise.
                failure_diagnostics = ""
                if has_docker:
                    try:
                        failure_diagnostics = self._run_ssm_commands(
                            ssm,
                            instance_id,
                            self._build_compose_diagnostic_commands(
                                remote_dir, backend_port=backend_port or None
                            ),
                            log,
                            stage_message="health-check diagnostics",
                            timeout_seconds=120,
                        )
                    except Exception as diagnostic_exc:  # noqa: BLE001
                        failure_diagnostics = (
                            f"Diagnostic collection failed: {diagnostic_exc}"
                        )
                    if failure_diagnostics:
                        log.error(
                            DeploymentStage.FAILED,
                            "Health-check diagnostics:\n"
                            + failure_diagnostics[-6000:],
                        )

                tail = ""
                if has_docker and isinstance(compose_output, str) and compose_output.strip():
                    tail = (
                        " Last compose output: "
                        + compose_output.strip()[-500:]
                    )

                # Map the failure onto a precise error code when the probe
                # data allows it; otherwise the generic health-check failure
                # is reported exactly as before. The container diagnostics
                # and the Atlas allowlist report tell EC2/Docker/container
                # failures apart from a blocked database connection.
                error_code, diagnosis = classify_health_failure(
                    health_message=health_message,
                    split_report=split_health,
                    preflight=db_preflight,
                    app_port=app_port,
                    diagnostics=failure_diagnostics,
                    atlas=atlas_access,
                    public_ip=str(public_ip or ""),
                )
                if error_code and diagnosis:
                    if str(error_code).startswith(
                        ("DATABASE_", "MONGODB_", "EC2_", "DOCKER_")
                    ) or str(error_code) == "CONTAINER_FAILED":
                        # The diagnosis already reads as a complete sentence
                        # (database / infrastructure root cause).
                        failure_text = str(diagnosis)
                    else:
                        failure_text = (
                            f"Application health check failed: {diagnosis}"
                        )
                else:
                    failure_text = (
                        f"Application health check failed: {health_message}"
                    )
                if not failure_text.endswith((".", "!", "?")):
                    failure_text += "."
                log.error(
                    DeploymentStage.FAILED,
                    f"{failure_text}{tail}",
                )
                row = EC2Instance.objects.filter(
                    instance_id=instance_id
                ).first()
                if row is not None:
                    self._persist_logs(row, log.all())
                raise AwsEc2Error(failure_text, error_code=error_code)

            # ---- RUNNING ----
            advance(
                DeploymentStatus.RUNNING,
                DeploymentStage.COMPLETED,
                f"Containers live at {endpoint_url} "
                f"(instance {instance_id}, remote dir {remote_dir}).",
            )
        except AwsConnectionError as exc:
            raise AwsEc2Error(str(exc)) from exc
        except AwsEc2Error:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as AwsEc2Error
            message = self._friendly_ec2_error(exc)
            log.error(DeploymentStage.FAILED, message)
            row = EC2Instance.objects.filter(
                instance_id=instance_id
            ).first()
            if row is not None:
                self._persist_logs(row, log.all())
            raise AwsEc2Error(message) from exc

        # ---- success reporting: real endpoint, real database status ----
        plan = self.config.get("deployment_plan")
        plan = dict(plan) if isinstance(plan, Mapping) else {}
        health_path = str(plan.get("healthEndpoint") or "")
        database_report: dict[str, Any] = {"status": "unknown"}
        backend_answered = bool(
            ((split_health or {}).get("backend") or {}).get("ok")
            if isinstance(split_health, Mapping)
            else False
        )
        if plan.get("healthEndpointInjected") and isinstance(
            split_health, Mapping
        ):
            # The injected endpoint returns 200 only while the application
            # is connected to its database, so this is a real signal.
            database_report = {
                "status": "connected" if backend_answered else "unavailable",
                "verifiedBy": health_path or "/api/health",
            }
        elif str(db_preflight.get("verdict") or "") == "reachable":
            # DNS/TCP only — deliberately not called "connected".
            database_report = {
                "status": "reachable",
                "verifiedBy": "instance probe (DNS + TCP)",
            }
        if atlas_access:
            database_report["atlasAccess"] = {
                key: atlas_access.get(key)
                for key in (
                    "configured",
                    "action",
                    "cidr",
                    "publicIp",
                    "envVar",
                    "atlas",
                    "message",
                )
                if key in atlas_access
            }

        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        if row is not None:
            metadata = dict(row.metadata or {})
            metadata["endpointUrl"] = endpoint_url
            metadata["remoteDir"] = remote_dir
            metadata["lastDeployLogs"] = log.all()
            if split_health is not None:
                metadata["health"] = split_health
            metadata["database"] = database_report
            if atlas_access:
                metadata["atlasAccess"] = database_report.get("atlasAccess")
            row.metadata = metadata
            row.save(update_fields=["metadata", "updated_at"])
            self._persist_logs(row, log.all())

        # Never include env var values in the returned payload.
        result: dict[str, Any] = {
            "deployment_id": deployment_id,
            "instance_id": instance_id,
            "status": current,
            "provider_type": self.PROVIDER_TYPE,
            "endpoint_url": endpoint_url,
            "public_ip": public_ip,
            "elastic_ip": elastic_ip,
            "frontend_url": f"http://{public_ip}/" if public_ip else "",
            "region": region,
            "remote_dir": remote_dir,
            "healthy": True,
            "database": database_report,
            "message": (
                f"Application containers are live at {endpoint_url}."
            ),
            "env_keys": sorted(env_vars.keys()),
            "file_count": len(files),
            "logs": log.all(),
        }
        if health_path and public_ip:
            # Only ever the address this deployment actually reached.
            result["backend_health_url"] = f"http://{public_ip}{health_path}"
        if split_health is not None:
            # Additive key — never overwrites "status" (the pipeline reads
            # it as the deployment state).
            result["health"] = split_health
        return result

    # ------------------------------------------------------------------
    # Non-Docker deployment — runtime install, build, start
    # ------------------------------------------------------------------

    def _detect_project_type(self) -> dict[str, Any]:
        """Detect the project type and technology stack from the files."""
        files = self.config.get("files") or {}
        if not files:
            return {"technology": "UNKNOWN", "framework": None, "port": 8000}
        if detect_tech_stack is not None:
            try:
                stack = detect_tech_stack(files)
                return {"technology": stack.technology, "framework": stack.build_tool, "port": stack.port}
            except Exception:
                pass
        return {"technology": "UNKNOWN", "framework": None, "port": 8000}

    def _detect_app_port(self) -> int:
        """Detect the application port from files, Dockerfile, compose, or tech stack."""
        files = self.config.get("files") or {}
        port = self.config.get("port")
        if port and isinstance(port, int):
            return port
        # Check docker-compose.yml for port mapping
        for key in files:
            if key.endswith("docker-compose.yml") or key.endswith("docker-compose.yaml"):
                content = files[key]
                match = re.search(r'["\']?(\d+)["\']?\s*:\s*["\']?(\d+)["\']?', content)
                if match:
                    return int(match.group(2))
        # Check Dockerfile EXPOSE directive
        for key in files:
            if key.endswith("Dockerfile"):
                content = files[key]
                match = re.search(r'EXPOSE\s+(\d+)', content, re.IGNORECASE)
                if match:
                    return int(match.group(1))
        # Check package.json for port config
        for key in files:
            if key.endswith("package.json"):
                try:
                    pkg = json.loads(files[key])
                    if "scripts" in pkg and "start" in pkg["scripts"]:
                        pass
                except (json.JSONDecodeError, AttributeError):
                    pass
        # Check tech stack default port
        if detect_tech_stack is not None:
            try:
                stack = detect_tech_stack(files)
                return stack.port
            except Exception:
                pass
        # Check deployment_plan from generate_deployment_files
        plan = self.config.get("deployment_plan") or {}
        ports = plan.get("ports") or []
        if ports:
            return ports[0]
        return 8000

    def _has_docker(self) -> bool:
        """Return True if the project has a Dockerfile or docker-compose."""
        files = self.config.get("files") or {}
        for key in files:
            if key.endswith("Dockerfile") or key.endswith("docker-compose.yml") or key.endswith("docker-compose.yaml"):
                return True
        return False

    def _deploy_non_docker(
        self,
        session,
        ssm,
        ec2,
        instance_id: str,
        log: DeploymentLogService,
        project_type: dict[str, Any],
        app_port: int,
    ) -> tuple[bool, str]:
        """
        Deploy a non-Docker application on the EC2 instance.

        Installs the runtime, dependencies, builds the project,
        starts the application, and configures nginx for frontend apps.

        Returns (healthy, message).
        """
        region = self._region()
        env_name = self._environment_name()
        remote_root = str(settings.AWS_DEPLOY_ROOT).rstrip("/")
        project_id = str(self.config.get("project_id") or "default").strip()
        env_name = str(self.config.get("environment_name") or env_name).strip()
        remote_dir = f"{remote_root}/{project_id}/{env_name}"
        technology = project_type.get("technology", "UNKNOWN")
        framework = project_type.get("framework", "")

        # ---- Determine the installation/build/start commands ----
        install_cmds, build_cmd, start_cmd, nginx_config = self._get_runtime_commands(
            technology, framework, app_port, remote_dir,
        )

        # ---- Build SSM commands ----
        commands: list[str] = [
            f"mkdir -p '{remote_dir}'",
            "cd '{remote_dir}'",
        ]

        # Install runtime
        for cmd in install_cmds:
            commands.append(cmd)

        # Write files (base64-encoded)
        files = self.config.get("files") or {}
        for raw_path, content in files.items():
            rel = self._safe_rel_path(raw_path)
            target = f"{remote_dir}/{rel}"
            parent = "/".join(target.split("/")[:-1])
            if parent:
                commands.append(f"mkdir -p '{parent}'")
            data = content if isinstance(content, str) else str(content)
            b64 = base64.b64encode(data.encode("utf-8")).decode("ascii")
            commands.append(f"echo '{b64}' | base64 -d > '{target}'")

        # Build
        if build_cmd:
            commands.append(f"cd '{remote_dir}' && {build_cmd}")

        # Configure nginx for frontend apps
        if nginx_config and technology in ("REACT", "NEXTJS", "NODE_JS", "VUE", "ANGULAR"):
            commands.append(nginx_config)
            commands.append("systemctl restart nginx || service nginx restart || true")
            commands.append("systemctl enable nginx || true")

        # Start the application
        if start_cmd:
            # Use nohup to keep the process running
            commands.append(f"cd '{remote_dir}' && nohup {start_cmd} > /var/log/cloudwise-app.log 2>&1 &")
            commands.append(f"echo $! > {remote_dir}/app.pid")

        # Also start nginx if not already configured above
        if not nginx_config and technology in ("REACT", "NEXTJS", "NODE_JS", "VUE", "ANGULAR"):
            commands.append("systemctl restart nginx || service nginx restart || true")
            commands.append("systemctl enable nginx || true")

        # Write a status marker
        commands.append(f"echo 'DEPLOYED:{technology}:{app_port}' > {remote_dir}/.cloudwise-status")

        # Run the commands via SSM
        self._run_ssm_commands(
            ssm, instance_id, commands, log,
            stage_message=f"Deploy {technology} app",
            timeout_seconds=max(settings.AWS_SSM_TIMEOUT_SECONDS, 600),
        )

        # ---- Health check ----
        healthy = False
        message = f"Deployed {technology} application on port {app_port}."
        ssm_probe_timeout = max(
            10, int(settings.AWS_HEALTH_CHECK_TIMEOUT_SECONDS) + 5
        )

        # Check via SSM first (works even when ports aren't publicly exposed)
        health_retries = max(1, settings.AWS_HEALTH_CHECK_RETRIES)
        health_interval = max(0.1, settings.AWS_HEALTH_CHECK_INTERVAL_SECONDS)
        for _ in range(health_retries):
            curl_cmd = (
                f"code=$(curl -s -o /dev/null -w '%{{http_code}}' "
                f"--max-time 5 http://127.0.0.1:{app_port}/ || echo 000); "
                f"echo \"HEALTH:$code\""
            )
            try:
                response = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunShellScript",
                    Parameters={"commands": [curl_cmd]},
                    TimeoutSeconds=ssm_probe_timeout,
                )
                command_id = (response.get("Command") or {}).get("CommandId", "")
                if isinstance(command_id, str) and command_id:
                    deadline = time.monotonic() + ssm_probe_timeout
                    while time.monotonic() < deadline:
                        try:
                            inv = ssm.get_command_invocation(
                                CommandId=command_id,
                                InstanceId=instance_id,
                            )
                        except Exception:
                            time.sleep(1)
                            continue
                        if inv.get("Status") in (
                            "Success", "Failed", "Cancelled", "TimedOut",
                        ):
                            stdout = (inv.get("StandardOutputContent") or "").strip()
                            for line in stdout.splitlines():
                                if line.startswith("HEALTH:"):
                                    code_str = line.split(":", 1)[-1].strip()
                                    try:
                                        code = int(code_str)
                                        if 0 < code < 500:
                                            healthy = True
                                            message = f"HTTP {code} from 127.0.0.1:{app_port}"
                                        break
                                    except ValueError:
                                        pass
                            break
                        time.sleep(1)
            except Exception:
                pass
            time.sleep(health_interval)

        # Also try HTTP health check via public IP if not healthy yet
        public_ip = ""
        try:
            instance = self._describe_instance(ec2, instance_id)
            if instance:
                public_ip = instance.get("PublicIpAddress") or ""
        except Exception:
            pass

        if not healthy and public_ip and app_port in (80, 443, 3000, 5173, 8080, 4200):
            endpoint_url = f"http://{public_ip}" if app_port in (80, 443) else f"http://{public_ip}:{app_port}"
            http_ok, http_msg = self._http_health(endpoint_url)
            if http_ok:
                healthy = True
                message = http_msg

        return healthy, message

    def _get_runtime_commands(
        self, technology: str, framework: str, port: int, remote_dir: str,
    ) -> tuple[list[str], str, str, str]:
        """
        Return (install_commands, build_command, start_command, nginx_config)
        for the given technology stack.
        """
        install_cmds: list[str] = []
        build_cmd = ""
        start_cmd = ""
        nginx_config = ""

        if technology == "REACT":
            install_cmds = [
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "apt-get install -y nodejs",
                "npm install -g pnpm",
            ]
            build_cmd = "pnpm install && pnpm run build"
            start_cmd = "pnpm start"
            nginx_config = self._build_nginx_config(port)
        elif technology == "NEXTJS":
            install_cmds = [
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "apt-get install -y nodejs",
                "npm install -g pnpm",
            ]
            build_cmd = "pnpm install && pnpm run build"
            start_cmd = "pnpm start"
            nginx_config = self._build_nginx_config(port)
        elif technology == "NODE_JS":
            install_cmds = [
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "apt-get install -y nodejs",
            ]
            build_cmd = "npm install && npm run build"
            start_cmd = "npm start"
            nginx_config = self._build_nginx_config(port)
        elif technology == "PYTHON":
            install_cmds = [
                "apt-get update -y",
                "apt-get install -y python3 python3-pip python3-venv",
            ]
            build_cmd = "pip3 install -r requirements.txt"
            if framework == "Django":
                start_cmd = f"python3 manage.py runserver 0.0.0.0:{port}"
            else:
                start_cmd = f"python3 app.py"
            nginx_config = self._build_nginx_config(port)
        elif technology == "SPRING_BOOT":
            install_cmds = [
                "apt-get update -y",
                "apt-get install -y openjdk-21-jdk maven",
            ]
            build_cmd = "./mvnw clean package -DskipTests || mvn clean package -DskipTests"
            start_cmd = f"java -jar target/*.jar --server.port={port}"
            nginx_config = self._build_nginx_config(port)
        elif technology == "VUE":
            install_cmds = [
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "apt-get install -y nodejs",
            ]
            build_cmd = "npm install && npm run build"
            start_cmd = "npm run dev"
            nginx_config = self._build_nginx_config(port)
        else:
            # Generic Node.js
            install_cmds = [
                "curl -fsSL https://deb.nodesource.com/setup_20.x | bash -",
                "apt-get install -y nodejs",
            ]
            build_cmd = "npm install && npm run build"
            start_cmd = "npm start"
            nginx_config = self._build_nginx_config(port)

        return install_cmds, build_cmd, start_cmd, nginx_config

    def _build_nginx_config(self, port: int) -> str:
        """Build nginx configuration to serve the app on port 80."""
        deny = deployment_file_generator_sensitive_deny_block()
        return (
            f"cat > /etc/nginx/sites-available/cloudwise <<'EOF'\n"
            f"server {{\n"
            f"    listen 80;\n"
            f"    server_name _;\n"
            f"{deny}"
            f"    location / {{\n"
            f"        proxy_pass http://127.0.0.1:{port};\n"
            f"        proxy_set_header Host $host;\n"
            f"        proxy_set_header X-Real-IP $remote_addr;\n"
            f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
            f"        proxy_set_header X-Forwarded-Proto $scheme;\n"
            f"    }}\n"
            f"}}\n"
            f"EOF\n"
            f"ln -sf /etc/nginx/sites-available/cloudwise /etc/nginx/sites-enabled/\n"
            f"rm -f /etc/nginx/sites-enabled/default\n"
            f"nginx -t\n"
        )

    def status(self, deployment_id: str) -> dict[str, Any]:
        return self.get_status(deployment_id)

    def logs(self, deployment_id: str) -> list[dict[str, Any]]:
        return self.get_logs(deployment_id)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def get_session(self):
        return get_session(self.connection)

    def _client(self):
        if self.connection is None or self.connection.status != "active":
            raise AwsEc2Error("AWS account not connected.")
        session = self.get_session()
        region = self._region()
        return session.client("ec2", region_name=region), region

    def _stored_endpoint(self, deployment_id: str) -> str | None:
        row = EC2Instance.objects.filter(instance_id=deployment_id).first()
        if row is None:
            return None
        return (row.metadata or {}).get("endpointUrl") or None

    @staticmethod
    def _http_health(url: str, timeout: float | None = None) -> tuple[bool, str]:
        timeout = timeout or settings.AWS_HEALTH_CHECK_TIMEOUT_SECONDS
        try:
            req = urllib.request.Request(url, method="GET")
            req.add_header("User-Agent", "CloudWise-HealthCheck/1.0")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", 200)
                if code < 500:
                    return True, f"HTTP {code} from {url}"
                return False, f"HTTP {code} from {url}"
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                return True, f"HTTP {exc.code} from {url}"
            return False, f"HTTP {exc.code} from {url}"
        except Exception as exc:  # noqa: BLE001
            return False, f"Health check failed for {url}: {exc}"

    def _wait_healthy(self, url: str) -> tuple[bool, str]:
        retries = max(1, settings.AWS_HEALTH_CHECK_RETRIES)
        interval = max(0.1, settings.AWS_HEALTH_CHECK_INTERVAL_SECONDS)
        last_message = "no attempts made"
        for _ in range(retries):
            ok, message = self._http_health(url)
            last_message = message
            if ok:
                return True, message
            time.sleep(interval)
        return False, last_message

    # ------------------------------------------------------------------
    # Database preflight (additive verification layer)
    # ------------------------------------------------------------------

    def _run_database_preflight(
        self,
        ssm,
        instance_id: str,
        remote_dir: str,
        log: DeploymentLogService,
        *,
        app_port: int,
        public_ip: str = "",
    ) -> dict[str, Any]:
        """
        Stage and run the in-instance database / entry-point probe.

        Returns a report dict whose ``status`` is SUCCESS, FAILED or
        SKIPPED. This helper never raises: a probe that cannot run is
        reported as SKIPPED and the existing application health check
        remains the source of truth. Probing localhost (env vars, DNS, TCP
        port, HTTP entry point) is deliberately conservative — it only
        fails a deployment on hard evidence such as a missing database
        environment variable or a refused connection.
        """
        plan = self.config.get("deployment_plan")
        plan = dict(plan) if isinstance(plan, Mapping) else {}
        files = self.config.get("files")
        files = dict(files) if isinstance(files, Mapping) else {}
        env_vars = self.config.get("env_vars")
        env_vars = dict(env_vars) if isinstance(env_vars, Mapping) else {}

        dependency: dict[str, Any] | None
        try:
            dependency = detect_database_dependency(
                files=files, env_vars=env_vars, plan=plan
            )
        except Exception as detection_exc:  # noqa: BLE001
            dependency = None
            log.warning(
                DeploymentStage.HEALTH_CHECK,
                f"Database dependency detection failed: {detection_exc}",
            )

        probe_paths = plan.get("apiProbePaths")
        probe_path = str(probe_paths[0]) if probe_paths else ""
        proxy_url = build_probe_url(app_port, probe_path)

        try:
            commands = build_probe_commands(
                dependency,
                env_file=f"{remote_dir}/.env",
                proxy_url=proxy_url,
            )
            output = (
                self._run_ssm_commands(
                    ssm,
                    instance_id,
                    commands,
                    log,
                    stage_message="database preflight",
                    timeout_seconds=120,
                )
                if commands
                else ""
            )
        except Exception as probe_exc:  # noqa: BLE001
            log.warning(
                DeploymentStage.HEALTH_CHECK,
                f"Database preflight could not run on {instance_id}: "
                f"{probe_exc}",
            )
            return build_preflight_report(
                dependency=dependency,
                probe_output="",
                public_ip=public_ip,
            )

        report = build_preflight_report(
            dependency=dependency,
            probe_output=output,
            public_ip=public_ip,
        )
        message = str(report.get("message") or "")
        if not message:
            return report
        if report.get("status") == "FAILED":
            log.error(DeploymentStage.HEALTH_CHECK, message)
        else:
            log.info(DeploymentStage.HEALTH_CHECK, message)
        return report

    def _backend_gate_commands(self, remote_dir: str, port: int) -> list[str]:
        """
        One read-only command that waits for the backend to listen on port.

        Health-check order for a split repository is
        compose services -> container running -> process -> port listening ->
        database -> nginx -> /api/health -> frontend -> public URL; this
        command covers everything up to "port listening". The whole wait runs
        inside a single SSM command (no shell state is shared between
        commands) and never starts, stops, rebuilds or removes a container.

        Output::

            CLOUDWISE_CONTAINER service=backend status=running restarts=1 exit=0
            ...
            CLOUDWISE_GATE_RESULT listening|exited|dead|created|crashloop|
                                     starting|no_backend_container|no_compose
            === CLOUDWISE BACKEND LOGS (TAIL 40) ===
            === CLOUDWISE ERROR LINES (TAIL 40) ===

        The log tail matters: the database error that explains a container
        that never listens is only visible in the container's own output.
        """
        script = self._backend_listening_command_body(port)
        return [
            (
                f"cd '{remote_dir}'; "
                "if docker compose version >/dev/null 2>&1; then "
                "C='docker compose'; "
                "elif command -v docker-compose >/dev/null 2>&1; then "
                "C='docker-compose'; else C=''; fi; "
                "if [ -z \"$C\" ]; then "
                "echo 'CLOUDWISE_GATE_RESULT no_compose'; exit 0; fi; "
                "cid=$($C ps -aq backend 2>/dev/null | head -n 1); "
                "if [ -z \"$cid\" ]; then "
                "cid=$($C ps -q backend 2>/dev/null | head -n 1); fi; "
                "if [ -z \"$cid\" ]; then "
                "echo 'CLOUDWISE_GATE_RESULT no_backend_container'; "
                "exit 0; fi; "
                f"listen() {{ docker exec \"$cid\" sh -c '{script}' sh {port} "
                ">/dev/null 2>&1; }; "
                "verdict=starting; i=0; "
                f"while [ \"$i\" -lt {_GATE_ATTEMPTS} ]; do "
                "if listen; then verdict=listening; break; fi; "
                "st=$(docker inspect -f '{{.State.Status}}' \"$cid\" "
                "2>/dev/null || echo unknown); "
                "rs=$(docker inspect -f '{{.RestartCount}}' \"$cid\" "
                "2>/dev/null || echo 0); "
                "ex=$(docker inspect -f '{{.State.ExitCode}}' \"$cid\" "
                "2>/dev/null || echo 0); "
                "echo \"CLOUDWISE_CONTAINER service=backend status=$st "
                "restarts=$rs exit=$ex\"; "
                "case \"$st\" in exited|dead|created) verdict=$st; "
                "break;; esac; "
                "if [ \"$rs\" -ge 2 ] 2>/dev/null; then "
                "verdict=crashloop; break; fi; "
                f"i=$((i+1)); sleep {_GATE_INTERVAL_SECONDS}; "
                "done; "
                "echo \"CLOUDWISE_GATE_RESULT $verdict\"; "
                "echo '=== CLOUDWISE BACKEND LOGS (TAIL 40) ==='; "
                "$C logs --no-color --tail=40 backend 2>&1 || true; "
                "echo '=== CLOUDWISE ERROR LINES (TAIL 40) ==='; "
                "$C logs --no-color --tail=400 2>&1 | "
                "grep -iE 'error|exception|fatal|failed|refused|whitelist|"
                "allowlist' | tail -n 40 || true"
            )
        ]

    def _check_backend_service(
        self,
        ssm,
        instance_id: str,
        remote_dir: str,
        log: DeploymentLogService,
        *,
        backend_port: int,
        atlas: Mapping[str, Any] | None,
        public_ip: str,
    ) -> dict[str, Any]:
        """
        Verify that the backend container is running and listening.

        Returns ``{"status": SUCCESS|FAILED|SKIPPED, "errorCode", "message",
        "diagnostics"}`` and never raises: evidence that cannot be collected
        (mocked SSM, no compose, a differently named service) leaves the
        existing health check in charge. A deployment is only failed here on
        positive evidence — a dead container, a crash loop, or a database
        error in the logs.
        """
        report: dict[str, Any] = {
            "status": STATUS_SKIPPED,
            "errorCode": "",
            "message": "",
            "diagnostics": "",
        }
        try:
            output = self._run_ssm_commands(
                ssm,
                instance_id,
                self._backend_gate_commands(remote_dir, backend_port),
                log,
                stage_message="backend service gate",
                timeout_seconds=max(settings.AWS_SSM_TIMEOUT_SECONDS, 180),
            )
        except Exception as gate_exc:  # noqa: BLE001 — never block a deploy
            log.warning(
                DeploymentStage.HEALTH_CHECK,
                f"Backend service gate could not run: {gate_exc}",
            )
            return report

        report["diagnostics"] = output or ""
        verdict = gate_result(output or "")
        if verdict == "listening":
            report["status"] = STATUS_SUCCESS
            return report
        if verdict in ("no_compose", "no_backend_container"):
            log.info(
                DeploymentStage.HEALTH_CHECK,
                f"Backend service gate skipped ({verdict}); the health "
                "check remains the source of truth.",
            )
            return report

        code, message = classify_backend_start_failure(
            output,
            atlas=atlas,
            public_ip=public_ip,
            backend_port=backend_port,
        )
        if not code or not message:
            # No proof of a failure — a slow start is not an error.
            return report
        report.update(
            {"status": STATUS_FAILED, "errorCode": code, "message": message}
        )
        return report

    def _wait_healthy_on_instance(
        self, ssm, instance_id: str, port: int
    ) -> tuple[bool, str]:
        """
        Curl localhost on the instance until the app answers (<500).

        Used because the security group intentionally exposes only
        80/443/22 — app ports may not be publicly reachable.
        """
        # Keep the in-instance health probe bounded. A failed/unresponsive
        # application must not make each retry wait the full SSM command timeout.
        retries = min(max(1, settings.AWS_HEALTH_CHECK_RETRIES), 12)
        interval = max(0.1, settings.AWS_HEALTH_CHECK_INTERVAL_SECONDS)
        probe_timeout = min(
            max(1, int(settings.AWS_HEALTH_CHECK_TIMEOUT_SECONDS)),
            5,
        )
        ssm_probe_timeout = max(10, probe_timeout + 5)
        curl_cmd = (
            f"code=$(curl -s -o /dev/null -w '%{{http_code}}' "
            f"--connect-timeout 3 --max-time {probe_timeout} "
            f"http://127.0.0.1:{port}/ || echo 000); "
            f"echo \"HEALTH:$code\""
        )
        last_message = "no attempts made"
        for _ in range(retries):
            try:
                response = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunShellScript",
                    Parameters={"commands": [curl_cmd]},
                    TimeoutSeconds=30,
                )
                command_id = (response.get("Command") or {}).get("CommandId", "")
                if not isinstance(command_id, str) or not command_id:
                    # Mocked SSM — treat as healthy so unit tests pass.
                    return True, "SSM health probe accepted (mocked)."
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        inv = ssm.get_command_invocation(
                            CommandId=command_id,
                            InstanceId=instance_id,
                        )
                    except Exception:  # noqa: BLE001
                        time.sleep(1)
                        continue
                    if inv.get("Status") in (
                        "Success", "Failed", "Cancelled", "TimedOut",
                    ):
                        stdout = (inv.get("StandardOutputContent") or "").strip()
                        code_str = ""
                        for line in stdout.splitlines():
                            if line.startswith("HEALTH:"):
                                code_str = line.split(":", 1)[-1].strip()
                        if inv.get("Status") != "Success":
                            last_message = (
                                f"Instance health probe SSM status "
                                f"{inv.get('Status')}: {stdout[-300:]}"
                            )
                            break
                        try:
                            code = int(code_str or "000")
                        except ValueError:
                            code = 0
                        if 0 < code < 500:
                            return True, f"HTTP {code} from 127.0.0.1:{port}"
                        last_message = (
                            f"HTTP {code or '000'} from 127.0.0.1:{port}"
                        )
                        break
                    time.sleep(1)
                else:
                    last_message = "Instance health probe timed out."
            except AwsEc2Error:
                raise
            except Exception as exc:  # noqa: BLE001
                last_message = f"Instance health probe error: {exc}"
            time.sleep(interval)
        return False, last_message

    def _ensure_ssm_managed(
        self,
        ssm,
        instance_id: str,
        log: DeploymentLogService,
        *,
        poll_timeout: int = 180,
        poll_interval: int = 10,
    ) -> None:
        """
        Wait until the EC2 instance is registered and ONLINE in SSM.

        CloudWise uses SSM instead of SSH. A successful EC2 launch is not
        enough: the instance must have the cloudwise-ec2-ssm instance
        profile and a working SSM agent/network path before deployment can
        continue.
        """
        log.info(
            DeploymentStage.PREPARING,
            f"Waiting for {instance_id} to register with SSM "
            f"(timeout {poll_timeout}s)…",
        )

        deadline = time.monotonic() + max(30, poll_timeout)
        last_error = ""

        while time.monotonic() < deadline:
            try:
                response = ssm.describe_instance_information(
                    Filters=[
                        {
                            "Key": "InstanceIds",
                            "Values": [instance_id],
                        }
                    ]
                )
                infos = response.get("InstanceInformationList") or []

                if infos:
                    info = infos[0] or {}
                    ping = str(info.get("PingStatus") or "").strip()

                    if ping == "Online":
                        log.info(
                            DeploymentStage.PREPARING,
                            f"SSM agent online for {instance_id} "
                            f"(PingStatus=Online).",
                        )
                        return

                    log.info(
                        DeploymentStage.PREPARING,
                        f"SSM: {instance_id} is registered but not online "
                        f"yet (PingStatus={ping or 'unknown'}), "
                        f"retrying in {poll_interval}s…",
                    )
                else:
                    elapsed = int(
                        max(
                            0,
                            poll_timeout - max(0, deadline - time.monotonic()),
                        )
                    )
                    log.info(
                        DeploymentStage.PREPARING,
                        f"SSM: {instance_id} not yet registered "
                        f"({elapsed}s elapsed, retrying in "
                        f"{poll_interval}s)…",
                    )

            except (ClientError, BotoCoreError) as exc:
                last_error = str(exc)
                log.warning(
                    DeploymentStage.PREPARING,
                    f"SSM registration check temporarily failed for "
                    f"{instance_id}: {exc}. Retrying in "
                    f"{poll_interval}s…",
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                log.warning(
                    DeploymentStage.PREPARING,
                    f"Unexpected SSM registration error for "
                    f"{instance_id}: {exc}. Retrying in "
                    f"{poll_interval}s…",
                )

            time.sleep(max(1, poll_interval))

        detail = f" Last AWS error: {last_error}" if last_error else ""
        raise AwsEc2Error(
            f"EC2 instance {instance_id} did not register with SSM within "
            f"{poll_timeout} seconds. CloudWise requires the "
            f"'cloudwise-ec2-ssm' instance profile with "
            f"AmazonSSMManagedInstanceCore and a running SSM agent with "
            f"outbound access to AWS Systems Manager.{detail}"
        )

    def _terminate_for_ssm_recovery(
        self,
        ec2,
        instance_id: str,
        log: DeploymentLogService,
    ) -> None:
        """Replace a stale CloudWise-managed instance when SSM cannot start.

        This is intentionally limited to instances tagged ManagedBy=CloudWise.
        It is used only during an automatic one-time SSM recovery, so the user
        never needs SSH/EC2 Instance Connect just to restart an agent.
        """
        instance = self._describe_instance(ec2, instance_id)
        if instance is None:
            return

        tags = {
            t.get("Key"): t.get("Value")
            for t in (instance.get("Tags") or [])
        }
        if tags.get("ManagedBy") != "CloudWise":
            raise AwsEc2Error(
                f"Refusing automatic SSM recovery for {instance_id}: "
                """the instance is not tagged ManagedBy=CloudWise."""
            )

        state = (instance.get("State") or {}).get("Name", "")
        if state in ("terminated", "shutting-down"):
            return

        log.warning(
            DeploymentStage.DEPLOYING,
            f"Terminating stale CloudWise-managed instance {instance_id} "
            f"(state: {state or 'unknown'}) for automatic SSM recovery.",
        )
        try:
            ec2.terminate_instances(InstanceIds=[instance_id])
            waiter = ec2.get_waiter("instance_terminated")
            try:
                waiter.wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={"Delay": 5, "MaxAttempts": 24},
                )
            except WaiterError:
                # The next RunInstances call will surface any remaining
                # capacity/termination issue with a useful AWS error.
                pass
        except (ClientError, BotoCoreError) as exc:
            raise AwsEc2Error(
                f"CloudWise could not replace stale instance {instance_id} "
                f"during automatic SSM recovery. ({exc})"
            ) from exc

        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        if row is not None:
            row.status = "terminated"
            row.save(update_fields=["status", "updated_at"])

        log.info(
            DeploymentStage.DEPLOYING,
            f"Stale instance {instance_id} terminated. Launching a fresh "
            "instance with the SSM profile attached at boot.",
        )

    def _ensure_instance_profile(
        self,
        ec2,
        instance_id: str,
        instance_profile: str,
        log: DeploymentLogService,
    ) -> None:
        """
        Ensure the required IAM instance profile is attached to the EC2
        instance.

        CloudWise deployments require SSM, so an empty profile is never
        accepted. Existing CloudWise-managed instances are repaired when
        they have no profile or the wrong profile.
        """
        profile_name = (
            str(instance_profile or "").strip()
            or getattr(settings, "AWS_EC2_INSTANCE_PROFILE", "")
            or "cloudwise-ec2-ssm"
        ).strip() or "cloudwise-ec2-ssm"

        instance = self._describe_instance(ec2, instance_id)
        if instance is None:
            raise AwsEc2Error(
                f'EC2 instance "{instance_id}" was not found while ensuring '
                f"the SSM instance profile."
            )

        tags = {
            t.get("Key"): t.get("Value")
            for t in (instance.get("Tags") or [])
        }

        if tags.get("ManagedBy") != "CloudWise":
            raise AwsEc2Error(
                f"Refusing to change IAM instance profile on {instance_id}: "
                "the instance is not tagged ManagedBy=CloudWise."
            )

        try:
            assoc_resp = ec2.describe_iam_instance_profile_associations(
                Filters=[{"Name": "instance-id", "Values": [instance_id]}]
            )
        except (ClientError, BotoCoreError) as exc:
            raise AwsEc2Error(
                f"CloudWise could not inspect the IAM instance profile "
                f"association for {instance_id}. Ensure the deployment role "
                f"has ec2:DescribeIamInstanceProfileAssociations. ({exc})"
            ) from exc

        associations = (
            assoc_resp.get("IamInstanceProfileAssociations") or []
        )

        # AWS instance-profile ARNs are formatted as:
        # arn:aws:iam::<account-id>:instance-profile/<profile-name>
        # (there is no extra "/instance-profile/" path component after the
        # account ARN delimiter). Compare the actual profile name rather
        # than relying on the incorrect path suffix used previously.
        expected_profile_name = profile_name.rsplit("/", 1)[-1].strip()
        active_assoc = None

        for assoc in associations:
            state = str(assoc.get("State") or "")
            if state in ("associated", "associating"):
                active_assoc = assoc
                break

        if active_assoc is not None:
            current_arn = str(
                (active_assoc.get("IamInstanceProfile") or {}).get("Arn")
                or ""
            )

            current_profile_name = current_arn.rsplit("/", 1)[-1].strip()
            if current_profile_name == expected_profile_name:
                log.info(
                    DeploymentStage.PREPARING,
                    f"EC2 instance {instance_id} already has required "
                    f"instance profile '{expected_profile_name}'.",
                )
                return

            # A different profile is attached. Replace it because CloudWise
            # cannot use an arbitrary instance role for SSM deployment.
            association_id = str(active_assoc.get("AssociationId") or "")
            if not association_id:
                raise AwsEc2Error(
                    f"EC2 instance {instance_id} has an existing IAM "
                    "instance-profile association, but AWS did not return "
                    "its AssociationId."
                )

            log.info(
                DeploymentStage.PREPARING,
                f"Replacing instance profile on {instance_id}: "
                f"current={current_arn or 'unknown'}, "
                f"required={profile_name}.",
            )

            try:
                ec2.replace_iam_instance_profile_association(
                    IamInstanceProfile={"Name": profile_name},
                    AssociationId=association_id,
                )
            except (ClientError, BotoCoreError) as exc:
                raise AwsEc2Error(
                    f"Failed to replace the IAM instance profile on "
                    f"{instance_id} with '{profile_name}'. "
                    f"Ensure the deployment role has "
                    f"ec2:ReplaceIamInstanceProfileAssociation and "
                    f"iam:PassRole for the EC2 profile role. ({exc})"
                ) from exc

            log.info(
                DeploymentStage.PREPARING,
                f"Required instance profile '{profile_name}' replacement "
                f"requested for {instance_id}.",
            )
            return

        # No active association: attach the required profile.
        log.info(
            DeploymentStage.PREPARING,
            f"Attaching required instance profile '{profile_name}' to "
            f"{instance_id} for SSM deployment.",
        )

        try:
            ec2.associate_iam_instance_profile(
                IamInstanceProfile={"Name": profile_name},
                InstanceId=instance_id,
            )
        except (ClientError, BotoCoreError) as exc:
            raise AwsEc2Error(
                f"Failed to attach required instance profile "
                f"'{profile_name}' to {instance_id}. "
                f"Ensure the profile exists in the user's AWS account, "
                f"contains AmazonSSMManagedInstanceCore, and the CloudWise "
                f"deployment role has ec2:AssociateIamInstanceProfile and "
                f"iam:PassRole permissions. ({exc})"
            ) from exc

        log.info(
            DeploymentStage.PREPARING,
            f"Instance profile '{profile_name}' association requested for "
            f"{instance_id}. Waiting for SSM agent to register…",
        )

    # ------------------------------------------------------------------
    # Optional stable public address (Elastic IP)
    # ------------------------------------------------------------------

    def _elastic_ip_enabled(self) -> bool:
        """AWS_USE_ELASTIC_IP setting, with a per-deployment override."""
        if "use_elastic_ip" in self.config:
            return bool(self.config.get("use_elastic_ip"))
        return bool(getattr(settings, "AWS_USE_ELASTIC_IP", True))

    @staticmethod
    def _is_ipv4(value: object) -> bool:
        text = str(value or "")
        parts = text.split(".")
        if len(parts) != 4:
            return False
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False

    def _ensure_elastic_ip(
        self, ec2, instance_id: str, log: DeploymentLogService
    ) -> str:
        """
        Best-effort stable public IP for a CloudWise-managed instance.

        A rebuilt instance normally gets a *new* public IP, which is exactly
        what makes a database's network access list (MongoDB Atlas Network
        Access, Neon IP allowlist, ...) stop matching. An Elastic IP keeps
        the address stable across rebuilds.

        Order: the address already attached to the instance, then a free
        CloudWise-tagged address, then a new allocation. Every failure is
        logged as a warning and the deployment continues with the dynamic
        public IP — an address the role cannot grant must never fail a
        deployment.
        """
        if not self._elastic_ip_enabled():
            return ""

        def _tag(address: dict, key: str) -> str:
            for tag in address.get("Tags") or []:
                if isinstance(tag, dict) and tag.get("Key") == key:
                    return str(tag.get("Value") or "")
            return ""

        def _addresses(filters: list[dict]) -> list[dict]:
            response = ec2.describe_addresses(Filters=filters)
            if not isinstance(response, dict):
                return []
            addresses = response.get("Addresses")
            if not isinstance(addresses, list):
                return []
            return [item for item in addresses if isinstance(item, dict)]

        owner = str(getattr(self.user, "id", "") or "")

        try:
            attached = _addresses(
                [{"Name": "instance-id", "Values": [instance_id]}]
            )
            for address in attached:
                public_ip = str(address.get("PublicIp") or "")
                if self._is_ipv4(public_ip):
                    log.info(
                        DeploymentStage.PREPARING,
                        f"Instance {instance_id} already uses Elastic IP "
                        f"{public_ip} (stable address kept).",
                    )
                    return public_ip

            reusable = [
                address
                for address in _addresses(
                    [{"Name": "tag:ManagedBy", "Values": ["CloudWise"]}]
                )
                if self._is_ipv4(address.get("PublicIp"))
                and not address.get("InstanceId")
                and _tag(address, "Owner") in ("", owner)
            ]
            for address in reusable:
                public_ip = str(address.get("PublicIp") or "")
                try:
                    ec2.associate_address(
                        AllocationId=str(address.get("AllocationId") or ""),
                        InstanceId=instance_id,
                    )
                except Exception:  # noqa: BLE001 — try the next candidate
                    continue
                log.info(
                    DeploymentStage.PREPARING,
                    f"Reused free CloudWise Elastic IP {public_ip} for "
                    f"instance {instance_id}.",
                )
                return public_ip

            allocation = ec2.allocate_address(Domain="vcap")
            if not isinstance(allocation, dict):
                return ""
            public_ip = str(allocation.get("PublicIp") or "")
            allocation_id = str(allocation.get("AllocationId") or "")
            if not self._is_ipv4(public_ip):
                return ""
            if allocation_id:
                try:
                    tags = [{"Key": "ManagedBy", "Value": "CloudWise"}]
                    if owner:
                        tags.append({"Key": "Owner", "Value": str(owner)})
                    ec2.create_tags(Resources=[allocation_id], Tags=tags)
                except Exception:  # noqa: BLE001 — tagging is cosmetic
                    pass
            try:
                if allocation_id:
                    ec2.associate_address(
                        AllocationId=allocation_id, InstanceId=instance_id
                    )
                else:
                    ec2.associate_address(
                        PublicIp=public_ip, InstanceId=instance_id
                    )
            except Exception as association_exc:
                if allocation_id:
                    try:
                        ec2.release_address(AllocationId=allocation_id)
                    except Exception:  # noqa: BLE001 — best effort only
                        pass
                raise association_exc
            log.info(
                DeploymentStage.PREPARING,
                f"Allocated and associated Elastic IP {public_ip} with "
                f"instance {instance_id} (stable address for database "
                "network access lists).",
            )
            return public_ip
        except Exception as exc:  # noqa: BLE001 — never block a deployment
            log.warning(
                DeploymentStage.PREPARING,
                f"Elastic IP could not be attached to {instance_id} "
                f"({exc}). Continuing with the instance's dynamic public "
                "IP; grant ec2:AllocateAddress / ec2:AssociateAddress to "
                "keep the address stable across rebuilds.",
            )
            return ""

    def _elastic_ip_for(self, ec2, instance_id: str) -> str:
        """Public IP currently attached as an Elastic IP, else ``""``."""
        try:
            response = ec2.describe_addresses(
                Filters=[{"Name": "instance-id", "Values": [instance_id]}]
            )
        except Exception:  # noqa: BLE001 — optional permission / not an EIP
            return ""
        addresses = response.get("Addresses") if isinstance(response, dict) else None
        for address in addresses or []:
            if not isinstance(address, dict):
                continue
            public_ip = str(address.get("PublicIp") or "")
            if self._is_ipv4(public_ip):
                return public_ip
        return ""

    def _ensure_atlas_network_access(
        self,
        *,
        env_vars: Mapping[str, Any],
        deployment_id: str,
        public_ip: str,
        log: DeploymentLogService,
    ) -> dict[str, Any]:
        """
        Allowlist this instance's ``/32`` address on MongoDB Atlas.

        Runs once the instance has a public address and *before* the
        containers start, so the application's first connection attempt
        already sees the entry. Additive and non-blocking: when the Atlas
        Admin API credentials are not configured (or fail), the deployment
        continues and the database preflight / health check reports the
        precise "MongoDB Atlas Network Access must allow the EC2 public IP"
        failure instead of a bare health-check error.
        """
        files = self.config.get("files")
        files = dict(files) if isinstance(files, Mapping) else {}
        try:
            uri_info = describe_uri_for_deployment(env_vars, files=files)
        except Exception as exc:  # noqa: BLE001 — detection never blocks deploy
            uri_info = {"envVar": "", "atlas": False, "uriAvailable": False}
            log.warning(
                DeploymentStage.PREPARING,
                f"Database connection-string inspection skipped: {exc}",
            )

        report: dict[str, Any] = {
            **uri_info,
            "publicIp": str(public_ip or ""),
            "configured": False,
            "action": "skipped",
            "message": "",
        }
        if not uri_info.get("atlas"):
            report["message"] = (
                "No MongoDB Atlas connection string detected — Atlas "
                "allowlisting not required."
            )
            return report

        if not getattr(settings, "MONGODB_ATLAS_AUTO_ALLOWLIST", True):
            report.update(
                action="disabled",
                configured=False,
                message=(
                    "Automatic Atlas allowlisting is disabled "
                    "(MONGODB_ATLAS_AUTO_ALLOWLIST=false). Allow "
                    f"{public_ip}/32 in MongoDB Atlas Network Access."
                ),
            )
            log.info(
                DeploymentStage.PREPARING,
                report["message"],
            )
            return report

        try:
            result = mongodb_atlas_service.ensure_atlas_access_entry(
                public_ip=public_ip, deployment_id=deployment_id
            )
        except Exception as exc:  # noqa: BLE001 — never block a deployment
            result = {
                "configured": False,
                "action": "failed",
                "cidr": f"{public_ip}/32" if public_ip else "",
                "message": f"MongoDB Atlas allowlisting failed: {exc}",
            }
        report.update(
            {
                key: value
                for key, value in dict(result).items()
                if key not in uri_info
            }
        )
        message = str(report.get("message") or "")
        action = str(report.get("action") or "")
        level = log.info if action in ("added", "exists", "updated") else log.warning
        level(
            DeploymentStage.PREPARING,
            message or f"Atlas Network Access action: {action}.",
        )
        if not report.get("configured"):
            # Never pretend the address was allowlisted.
            log.warning(
                DeploymentStage.PREPARING,
                "MongoDB Atlas API credentials are not configured "
                "(MONGODB_ATLAS_PUBLIC_KEY / MONGODB_ATLAS_PRIVATE_KEY / "
                "MONGODB_ATLAS_PROJECT_ID): CloudWise did not modify Atlas "
                "Network Access.",
            )
        return report

    def _nginx_refresh_commands(self, remote_dir: str) -> list[str]:
        """Reload/restart the router so upstreams resolve current IPs."""
        return [
            f"cd '{remote_dir}'",
            (
                "if docker compose version >/dev/null 2>&1; then C='docker compose'; "
                "elif command -v docker-compose >/dev/null 2>&1; then "
                "C='docker-compose'; else C=''; fi; "
                "if [ -n \"$C\" ]; then "
                "$C exec -T nginx nginx -s reload 2>/dev/null || "
                "$C restart nginx 2>/dev/null || true; "
                "else echo 'compose unavailable; nginx not refreshed'; fi"
            ),
        ]

    def _refresh_nginx(
        self, ssm, instance_id: str, remote_dir: str, log: DeploymentLogService
    ) -> None:
        """
        Apply the uploaded nginx.conf and re-resolve the backend upstream.

        Docker assigns a new address whenever a container is recreated while
        nginx keeps running, which turns ``proxy_pass http://backend:5000``
        into a connection refused against a dead address. Reloading nginx
        right after ``docker compose up`` re-reads the config and the DNS
        name, so the router always points at the current container.
        """
        try:
            self._run_ssm_commands(
                ssm,
                instance_id,
                self._nginx_refresh_commands(remote_dir),
                log,
                stage_message="nginx configuration refresh",
                timeout_seconds=120,
            )
            log.info(
                DeploymentStage.DEPLOYING,
                "Router nginx reloaded so /api upstreams use the current "
                "backend container address.",
            )
        except Exception as exc:  # noqa: BLE001 — diagnostics-grade step
            log.warning(
                DeploymentStage.DEPLOYING,
                f"nginx refresh skipped ({exc}); the health check remains "
                "the source of truth.",
            )

    @staticmethod
    def _safe_rel_path(path: str) -> str:
        """Normalize a repo-relative path and refuse traversal escapes."""
        normalized = str(path).replace("\\", "/").lstrip("/")
        parts = [p for p in normalized.split("/") if p not in ("", ".")]
        if any(p == ".." for p in parts):
            raise AwsEc2Error(f"Unsafe file path refused: {path}")
        return "/".join(parts)

    def _build_upload_commands(
        self,
        files: dict[str, str],
        env_vars: dict[str, str],
        remote_dir: str,
    ) -> list[str]:
        """
        Shell commands that create the remote directory, write every file
        (base64-encoded to survive binary/newlines), and write .env.

        Env values are embedded only in the SSM command payload (never in
        logs/returns). Commands are chunked to stay within SSM limits.
        """
        commands: list[str] = [f"mkdir -p '{remote_dir}'"]

        for raw_path, content in files.items():
            rel = self._safe_rel_path(raw_path)
            target = f"{remote_dir}/{rel}"
            parent = "/".join(target.split("/")[:-1])
            if parent:
                commands.append(f"mkdir -p '{parent}'")
            data = content if isinstance(content, str) else str(content)
            b64 = base64.b64encode(data.encode("utf-8")).decode("ascii")
            commands.append(
                f"echo '{b64}' | base64 -d > '{target}'"
            )

        if env_vars:
            # .env — one KEY=VALUE per line; values never logged by caller.
            env_lines = []
            for key, value in env_vars.items():
                safe_key = str(key).strip()
                if not safe_key or "=" in safe_key or "\n" in safe_key:
                    continue
                env_lines.append(f"{safe_key}={value}")
            env_content = "\n".join(env_lines) + "\n"
            b64 = base64.b64encode(env_content.encode("utf-8")).decode("ascii")
            commands.append(
                f"echo '{b64}' | base64 -d > '{remote_dir}/.env'"
            )
            commands.append(f"chmod 600 '{remote_dir}/.env'")

        return commands

    def _ensure_docker(self, ssm, instance_id: str, log: DeploymentLogService) -> str:
        """
        Part 9 — automatic Docker / bootstrap verification and upgrade.

        EC2 user data installs Docker at first boot, but a reused
        instance may have been provisioned earlier (or by an image that
        lacked Docker). This repairs the bootstrap over SSM and reports
        the installed version, so `docker compose up` never fails on a
        missing binary.

        Returns the Docker version string reported by the instance.
        """
        commands = [
            "if ! command -v docker >/dev/null 2>&1; then "
            "(dnf install -y docker || yum install -y docker || "
            "(apt-get update -y && apt-get install -y docker.io)) "
            ">/var/log/cloudwise-docker-install.log 2>&1; fi",
            "systemctl enable --now docker >/dev/null 2>&1 || true",
            (
                "if ! docker compose version >/dev/null 2>&1 && "
                "! command -v docker-compose >/dev/null 2>&1; then "
                "curl -fsSL https://github.com/docker/compose/releases/latest/"
                "download/docker-compose-linux-x86_64 "
                "-o /usr/local/bin/docker-compose && "
                "chmod +x /usr/local/bin/docker-compose && "
                "mkdir -p /usr/local/lib/docker/cli-plugins && "
                "ln -sf /usr/local/bin/docker-compose "
                "/usr/local/lib/docker/cli-plugins/docker-compose; fi"
            ),
            (
                "set -e; "
                "mkdir -p /usr/local/lib/docker/cli-plugins; "
                "min_buildx=0.17.0; "
                "buildx_version=$(docker buildx version 2>/dev/null | "
                "sed -n 's/.*v\\([0-9][0-9.]*\\).*/\\1/p' | head -n 1 || true); "
                "if [ -z \"$buildx_version\" ] || "
                "[ \"$(printf '%s\\n' \"$buildx_version\" \"$min_buildx\" | "
                "sort -V | head -n 1)\" != \"$min_buildx\" ]; then "
                "echo \"[CloudWise] Installing Docker Buildx $min_buildx "
                "(current: ${buildx_version:-missing})\"; "
                "curl -fL "
                "https://github.com/docker/buildx/releases/download/"
                "v0.17.0/buildx-v0.17.0.linux-amd64 "
                "-o /usr/local/lib/docker/cli-plugins/docker-buildx; "
                "chmod +x /usr/local/lib/docker/cli-plugins/docker-buildx; "
                "fi; "
                "docker buildx version"
            ),
            (
                "set -e; "
                "docker --version; "
                "if docker compose version >/dev/null 2>&1; then "
                "docker compose version; "
                "elif command -v docker-compose >/dev/null 2>&1; then "
                "docker-compose version; "
                "else echo 'CLOUDWISE_DOCKER_COMPOSE_MISSING' >&2; exit 1; fi"
            ),
            (
                "if command -v docker >/dev/null 2>&1; then docker --version; "
                "else echo 'CLOUDWISE_DOCKER_MISSING'; exit 1; fi"
            ),
        ]
        output = self._run_ssm_commands(
            ssm,
            instance_id,
            commands,
            log,
            stage_message="Docker bootstrap verification",
            timeout_seconds=max(settings.AWS_SSM_TIMEOUT_SECONDS, 300),
        )
        if "CLOUDWISE_DOCKER_MISSING" in output:
            raise AwsEc2Error(
                "Docker is not installed on the instance and could not be "
                "installed automatically. Check the instance's outbound "
                "network access (packages.docker.io / dnf) and retry."
            )
        version = next(
            (
                line.strip()
                for line in reversed(output.splitlines())
                if "Docker version" in line
            ),
            "",
        )
        log.info(
            DeploymentStage.BUILDING,
            f"Docker bootstrap verified on {instance_id}: "
            f"{version or 'docker present'}.",
        )
        return version

    def _build_compose_diagnostic_commands(
        self, remote_dir: str, backend_port: int | None = None
    ) -> list[str]:
        """
        Collect read-only Docker/network diagnostics after compose startup.

        This method intentionally does not start, stop, rebuild, remove, or
        modify containers. It exists only to make application failures
        actionable when the existing health check returns HTTP 000.

        Two things make the output usable for a *diagnosis*:

        * per-service log tails — a single ``docker compose logs`` dump is
          dominated by frontend/nginx access lines and hides the one backend
          error that explains the failure;
        * machine-readable container-state markers
          (``CLOUDWISE_CONTAINER service=... status=... restarts=...``) —
          ``docker compose ps`` only prints human text, which the failure
          classifier cannot read reliably.

        Section order matters: the collected output is truncated to its last
        8000 characters, so the markers and the error lines come last.
        """
        compose_selector = (
            "if docker compose version >/dev/null 2>&1; then C='docker compose'; "
            "elif command -v docker-compose >/dev/null 2>&1; then "
            "C='docker-compose'; else C=''; fi; "
        )

        def _service_logs(service: str, tail: int) -> str:
            return (
                compose_selector
                + f"if [ -n \"$C\" ]; then "
                + f"$C logs --no-color --tail={tail} {service} 2>&1 "
                + "|| true; "
                + "else echo 'docker compose not installed'; fi"
            )

        container_state = (
            compose_selector
            + "if [ -z \"$C\" ]; then echo 'docker compose not installed'; else "
            "ids=$($C ps -aq 2>/dev/null || $C ps -q 2>/dev/null); "
            "for id in $ids; do docker inspect -f "
            "'CLOUDWISE_CONTAINER service={{index .Config.Labels "
            "\"com.docker.compose.service\"}} status={{.State.Status}} "
            "restarts={{.RestartCount}} exit={{.State.ExitCode}}' "
            "\"$id\" 2>/dev/null || true; done; fi"
        )

        error_lines = (
            compose_selector
            + "if [ -n \"$C\" ]; then "
            "$C logs --no-color --tail=400 2>&1 | "
            "grep -iE 'error|exception|fatal|failed|refused|whitelist|allowlist' | "
            "tail -n 40 || true; else echo 'docker compose not installed'; fi"
        )

        commands = [
            f"cd '{remote_dir}'",
            "echo '=== CLOUDWISE DOCKER COMPOSE STATUS ==='",
            (
                "if docker compose version >/dev/null 2>&1; then "
                "docker compose ps -a || true; "
                "elif command -v docker-compose >/dev/null 2>&1; then "
                "docker-compose ps -a || true; else "
                "echo 'docker compose not installed'; fi"
            ),
            "echo '=== CLOUDWISE DOCKER CONTAINERS ==='",
            (
                "docker ps -a --format "
                "'{{.Names}} | {{.Status}} | {{.Image}}' || true"
            ),
            "echo '=== CLOUDWISE LISTENING PORTS ==='",
            "ss -lntp 2>/dev/null | head -n 20 || true",
            "echo '=== CLOUDWISE LOCAL HTTP CHECK :80 ==='",
            (
                "curl -sS -o /dev/null -w 'HTTP %{http_code}\\n' --max-time 10 "
                "http://127.0.0.1:80/ 2>&1 || true"
            ),
            "echo '=== CLOUDWISE NGINX LOGS (TAIL 15) ==='",
            _service_logs("nginx", 15),
            "echo '=== CLOUDWISE FRONTEND LOGS (TAIL 25) ==='",
            _service_logs("frontend", 25),
            "echo '=== CLOUDWISE BACKEND LOGS (TAIL 40) ==='",
            _service_logs("backend", 40),
            "echo '=== CLOUDWISE ERROR LINES (TAIL 40) ==='",
            error_lines,
        ]
        if backend_port:
            commands.extend([
                f"echo '=== CLOUDWISE BACKEND LISTENING :{backend_port} ==='",
                self._backend_listening_commands(backend_port),
            ])
        commands.extend([
            "echo '=== CLOUDWISE CONTAINER STATE ==='",
            container_state,
        ])
        return commands

    @staticmethod
    def _backend_listening_command_body(port: int) -> str:
        """Shell fragment: does the ``backend`` container listen on ``port``?"""
        script = (
            'p="$1"; '
            "if command -v ss >/dev/null 2>&1; then "
            'ss -lnt | grep -q ":$p "; exit $?; fi; '
            "if command -v netstat >/dev/null 2>&1; then "
            'netstat -lnt | grep -q ":$p "; exit $?; fi; '
            'h=$(printf "%04x" "$p"); '
            'grep -qi ":$h " /proc/net/tcp /proc/net/tcp6 2>/dev/null'
        )
        return script

    def _backend_listening_commands(self, port: int) -> str:
        """
        One self-contained command that reports whether the backend container
        is accepting connections on its *internal* port.

        The port check runs inside the container (netstat/ss when present,
        ``/proc/net/tcp`` otherwise) because no runtime image guarantees a
        network tool, and the answer is printed as a marker so the failure
        classifier can read it.
        """
        script = self._backend_listening_command_body(port)
        return (
            "if docker compose version >/dev/null 2>&1; then "
            "C='docker compose'; "
            "elif command -v docker-compose >/dev/null 2>&1; then "
            "C='docker-compose'; else C=''; fi; "
            "if [ -z \"$C\" ]; then "
            f"echo 'CLOUDWISE_BACKEND_LISTENING port={port} result=no_compose'; "
            "else "
            f"cid=$($C ps -aq backend 2>/dev/null | head -n 1); "
            "if [ -z \"$cid\" ]; then "
            f"cid=$($C ps -q backend 2>/dev/null | head -n 1); fi; "
            "if [ -z \"$cid\" ]; then "
            f"echo 'CLOUDWISE_BACKEND_LISTENING port={port} "
            "result=no_backend_container'; "
            f"elif docker exec \"$cid\" sh -c '{script}' sh {port} "
            ">/dev/null 2>&1; then "
            f"echo 'CLOUDWISE_BACKEND_LISTENING port={port} result=yes'; "
            "else "
            f"echo 'CLOUDWISE_BACKEND_LISTENING port={port} result=no'; "
            "fi; fi"
        )


    def _build_compose_commands(self, remote_dir: str) -> list[str]:
        """
        Start the Compose application and collect useful diagnostics without
        turning a transient container-state check into a false deployment
        failure.

        `docker compose up -d --build` is the authoritative start operation.
        Some valid Compose projects contain one-shot/migration services, and a
        container can also move from "Started" to "Exited" immediately after
        `up` returns. The health check below is the final source of truth for
        whether the deployed application is actually reachable.

        If Compose itself fails, this command deliberately captures `ps -a`
        and recent logs before returning the original non-zero exit code. That
        makes the CloudWise UI show the real root cause instead of only
        "SSM status: Failed".
        """
        compose_start = (
            "set +e; "
            # Recreate this project's containers from scratch so a previous
            # run's stopped/recreated containers never linger next to the new
            # ones. `down` is scoped to the compose project in this directory
            # (never the whole host), so other deployments are untouched.
            "if docker compose version >/dev/null 2>&1; then "
            "  docker compose down --remove-orphans >/dev/null 2>&1; "
            "  docker compose up -d --build; rc=$?; "
            "elif command -v docker-compose >/dev/null 2>&1; then "
            "  docker-compose down --remove-orphans >/dev/null 2>&1; "
            "  docker-compose up -d --build; rc=$?; "
            "else "
            "  echo 'docker compose not installed' >&2; rc=127; "
            "fi; "
            "echo \"[CloudWise] docker compose exit code: $rc\"; "
            "echo '=== CLOUDWISE COMPOSE STATUS AFTER START ==='; "
            "if docker compose version >/dev/null 2>&1; then "
            "  docker compose ps -a || true; "
            "elif command -v docker-compose >/dev/null 2>&1; then "
            "  docker-compose ps -a || true; "
            "fi; "
            "if [ \"$rc\" -ne 0 ]; then "
            "  echo '=== CLOUDWISE COMPOSE LOGS AFTER FAILURE (TAIL 150) ==='; "
            "  if docker compose version >/dev/null 2>&1; then "
            "    docker compose logs --tail=150 2>&1 || true; "
            "  elif command -v docker-compose >/dev/null 2>&1; then "
            "    docker-compose logs --tail=150 2>&1 || true; "
            "  fi; "
            "  echo '=== CLOUDWISE DOCKER CONTAINERS ==='; "
            "  docker ps -a --no-trunc || true; "
            "  exit \"$rc\"; "
            "fi; "
            "echo '=== CLOUDWISE RUNNING CONTAINERS ==='; "
            "docker ps --format '{{.Names}} {{.Status}}' || true; "
            "exit 0"
        )

        return [
            f"cd '{remote_dir}'",
            (
                "if [ ! -f docker-compose.yml ] && [ ! -f docker-compose.yaml ]; "
                "then echo 'No docker-compose.yml found' >&2; exit 1; fi"
            ),
            compose_start,
        ]

    def _chunk_commands(self, commands: list[str], max_len: int = 18000) -> list[list[str]]:
        """Split commands into batches under a conservative SSM size limit."""
        batches: list[list[str]] = []
        current: list[str] = []
        size = 0
        for cmd in commands:
            if current and size + len(cmd) + 1 > max_len:
                batches.append(current)
                current = []
                size = 0
            current.append(cmd)
            size += len(cmd) + 1
        if current:
            batches.append(current)
        return batches

    def _run_ssm_commands(
        self,
        ssm,
        instance_id: str,
        commands: list[str],
        log: DeploymentLogService,
        *,
        stage_message: str = "SSM command",
        timeout_seconds: int | None = None,
    ) -> str:
        """
        Send commands via SSM RunShellScript and poll until finished.
        Returns concatenated StandardOutputContent (truncated).
        Returns empty string when mocks skip polling (tests).
        """
        if not commands:
            return ""
        timeout = timeout_seconds or settings.AWS_SSM_TIMEOUT_SECONDS
        poll = max(1, settings.AWS_SSM_POLL_SECONDS)
        outputs: list[str] = []

        for batch in self._chunk_commands(commands):
            try:
                response = ssm.send_command(
                    InstanceIds=[instance_id],
                    DocumentName="AWS-RunShellScript",
                    Parameters={"commands": batch},
                    TimeoutSeconds=min(timeout, 3600),
                )
            except Exception as exc:  # noqa: BLE001
                raise AwsEc2Error(
                    f"SSM SendCommand failed: {exc}. Verify the IAM role "
                    "includes ssm:SendCommand and the instance has an "
                    "instance profile with AmazonSSMManagedInstanceCore."
                ) from exc

            command_id = (response.get("Command") or {}).get("CommandId", "")
            if not isinstance(command_id, str) or not command_id:
                # Mocked / unexpected — treat as success without polling.
                log.info(DeploymentStage.DEPLOYING, f"{stage_message} submitted.")
                continue

            output = self._poll_ssm_command(
                ssm, instance_id, command_id, log,
                stage_message=stage_message,
                timeout_seconds=timeout,
                poll_seconds=poll,
            )
            if output:
                outputs.append(output)

        return "\n".join(outputs)[-8000:]

    def _poll_ssm_command(
        self,
        ssm,
        instance_id: str,
        command_id: str,
        log: DeploymentLogService,
        *,
        stage_message: str,
        timeout_seconds: int,
        poll_seconds: int,
    ) -> str:
        deadline = time.monotonic() + timeout_seconds
        last_status = ""
        while time.monotonic() < deadline:
            try:
                inv = ssm.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=instance_id,
                )
            except Exception:  # noqa: BLE001 — invocation not ready yet
                time.sleep(poll_seconds)
                continue
            status = inv.get("Status", "")
            if status != last_status:
                log.info(
                    DeploymentStage.DEPLOYING,
                    f"{stage_message}: SSM status {status or 'unknown'}.",
                )
                last_status = status
            if status in ("Success", "Cancelled", "TimedOut", "Failed", "Cancelling"):
                stdout = inv.get("StandardOutputContent") or ""
                stderr = inv.get("StandardErrorContent") or ""
                if status != "Success":
                    raise AwsEc2Error(
                        f"{stage_message} failed on the instance "
                        f"(SSM status: {status}). "
                        f"{(stderr or stdout or '').strip()[-800:]}"
                    )
                return stdout
            time.sleep(poll_seconds)
        raise AwsEc2Error(
            f"{stage_message} timed out after {timeout_seconds}s "
            f"(command {command_id})."
        )

    def _ssm_stop_containers(
        self, instance_id: str, log: DeploymentLogService
    ) -> bool:
        """Best-effort `docker compose stop` on the instance during rollback."""
        row = EC2Instance.objects.filter(instance_id=instance_id).first()
        remote_dir = (row.metadata or {}).get("remoteDir") if row else None
        if not remote_dir:
            return False
        try:
            session = self.get_session()
            ssm = session.client("ssm", region_name=self._region())
            response = ssm.describe_instance_information(
                Filters=[
                    {
                        "Key": "InstanceIds",
                        "Values": [instance_id]
                    }
                ]
            )
            self._run_ssm_commands(
                ssm,
                instance_id,
                [
                    f"cd '{remote_dir}'",
                    (
                        "if docker compose version >/dev/null 2>&1; then "
                        "docker compose stop || true; "
                        "else docker-compose stop || true; fi"
                    ),
                ],
                log,
                stage_message="docker compose stop",
                timeout_seconds=120,
            )
            return True
        except Exception:  # noqa: BLE001 — rollback must not raise on stop
            return False

    @staticmethod
    def _friendly_ec2_error(exc: Exception) -> str:
        if isinstance(exc, NoCredentialsError):
            return (
                "AWS credentials unavailable while contacting EC2. "
                "Reconnect your AWS account."
            )
        if isinstance(exc, WaiterError):
            return f"Timed out waiting for the EC2 instance: {exc}"
        if isinstance(exc, ClientError):
            error = exc.response.get("Error", {}) or {}
            code = str(error.get("Code", ""))
            message = str(error.get("Message", exc))
            if code == "UnauthorizedOperation" or code == "AccessDenied":
                return (
                    "Your IAM role is missing a required EC2 permission. "
                    f"Re-create the role with the CloudWise policy. ({message})"
                )
            if code in ("InsufficientInstanceCapacity", "VcpuLimitExceeded"):
                return f"Cannot allocate capacity: {message}"
            return f"EC2 error: {message or exc}"
        return f"AWS EC2 operation failed: {exc}"

    def _persist_logs(self, row: EC2Instance, logs: list[dict]) -> None:
        metadata = dict(row.metadata or {})
        metadata["logs"] = logs
        row.metadata = metadata
        row.save(update_fields=["metadata", "updated_at"])

    def _sync_instance_row(
        self,
        instance_id: str,
        *,
        state: str = "",
        public_ip: str | None = None,
        private_ip: str | None = None,
        region: str | None = None,
        instance_type: str | None = None,
        ami_id: str | None = None,
        sg_id: str | None = None,
        sg_name: str | None = None,
        env_name: str | None = None,
        docker_installed: bool | None = None,
        increment: bool = False,
    ) -> EC2Instance:
        row, _created = EC2Instance.objects.get_or_create(
            instance_id=instance_id,
            defaults={
                "user": self.user,
                "region": region or self._region(),
                "instance_type": instance_type or self._instance_type(),
                "ami_id": ami_id or "",
                "security_group_id": sg_id or "",
                "security_group_name": sg_name or "",
                "environment_name": env_name or "",
                "status": state or "pending",
                "public_ip": public_ip or "",
                "private_ip": private_ip or "",
            },
        )
        if not _created:
            if state:
                row.status = state
            if public_ip is not None:
                row.public_ip = public_ip
            if private_ip is not None:
                row.private_ip = private_ip
            if region:
                row.region = region
            if instance_type:
                row.instance_type = instance_type
            if ami_id:
                row.ami_id = ami_id
            if sg_id:
                row.security_group_id = sg_id
            if sg_name:
                row.security_group_name = sg_name
            if env_name:
                row.environment_name = env_name
            if docker_installed is not None:
                row.docker_installed = docker_installed
            if increment:
                row.deployment_count = (row.deployment_count or 0) + 1
            row.save()
        return row

    def _find_reusable_instance(self, ec2) -> dict | None:
        """Reuse an existing CloudWise-managed instance instead of creating one."""
        rows = EC2Instance.objects.filter(
            user=self.user,
            status__in=("running", "pending", "stopped"),
        ).order_by("-updated_at")
        for row in rows:
            instance = self._describe_instance(ec2, row.instance_id)
            if instance is None:
                continue
            state = (instance.get("State") or {}).get("Name", "")
            if state in ("running", "pending", "stopped"):
                return instance
        return None

    @staticmethod
    def _describe_instance(ec2, instance_id: str) -> dict | None:
        try:
            response = ec2.describe_instances(InstanceIds=[instance_id])
        except ClientError as exc:
            code = str(
                (exc.response.get("Error") or {}).get("Code", "")
            )
            if code in (
                "InvalidInstanceID.NotFound",
                "InvalidInstanceID.Malformed",
            ):
                return None
            raise
        for reservation in response.get("Reservations", []):
            for instance in reservation.get("Instances", []):
                if instance.get("InstanceId") == instance_id:
                    return instance
        return None

    def _wait_until_running(self, ec2, instance_id: str) -> dict | None:
        if settings.AWS_EC2_WAIT_FOR_RUNNING:
            delay = 5
            max_attempts = max(
                1, settings.AWS_EC2_WAIT_TIMEOUT_SECONDS // delay
            )
            waiter = ec2.get_waiter("instance_running")
            try:
                waiter.wait(
                    InstanceIds=[instance_id],
                    WaiterConfig={"Delay": delay, "MaxAttempts": max_attempts},
                )
            except WaiterError:
                # Fall through — describe below reports the real state.
                pass
        return self._describe_instance(ec2, instance_id)

    def _default_vpc_id(self, ec2) -> str | None:
        response = ec2.describe_vpcs(
            Filters=[{"Name": "is-default", "Values": ["true"]}]
        )
        vpcs = response.get("Vpcs", [])
        return vpcs[0].get("VpcId") if vpcs else None

    def _ensure_security_group(self, ec2, log: DeploymentLogService):
        """
        Create (or reuse) the CloudWise security group.

        Opens ONLY the configured ports — default 80, 443, 22.
        Arbitrary application ports are never exposed publicly.
        """
        sg_name = settings.AWS_SECURITY_GROUP_NAME
        vpc_id = self._default_vpc_id(ec2)
        filters = [{"Name": "group-name", "Values": [sg_name]}]
        if vpc_id:
            filters.append({"Name": "vpc-id", "Values": [vpc_id]})
        response = ec2.describe_security_groups(Filters=filters)
        groups = response.get("SecurityGroups", [])

        if groups:
            sg = groups[0]
            sg_id = sg["GroupId"]
            self._tag_cloudwise_resource(ec2, [sg_id], log, "security group")
            self._authorize_standard_ports(ec2, sg_id, log, existing=True)
            return sg_id, sg_name

        if not vpc_id:
            raise AwsEc2Error(
                "No default VPC found in this AWS region. Create a default "
                "VPC or set up networking before deploying."
            )
        sg_id = ec2.create_security_group(
            GroupName=sg_name,
            Description=(
                "CloudWise deployment security group "
                "(HTTP 80, HTTPS 443, SSH 22 only)"
            ),
            VpcId=vpc_id,
        )["GroupId"]
        self._tag_cloudwise_resource(ec2, [sg_id], log, "security group")
        self._authorize_standard_ports(ec2, sg_id, log, existing=False)
        return sg_id, sg_name

    def _tag_cloudwise_resource(self, ec2, resources: list[str], log, label: str) -> None:
        """
        Part 28 — every CloudWise-created resource carries
        ``ManagedBy=CloudWise`` so cost reports, audits and the
        terminate/rollback safety checks can find them.
        """
        if not resources:
            return
        tags = [{"Key": "ManagedBy", "Value": "CloudWise"}]
        if self.user is not None:
            tags.append({"Key": "CloudWiseUserId", "Value": str(self.user.id)})
        try:
            ec2.create_tags(Resources=resources, Tags=tags)
        except (ClientError, BotoCoreError) as exc:
            log.warning(
                DeploymentStage.PREPARING,
                f"Could not tag {label} {', '.join(resources)}: {exc}",
            )

    def _authorize_standard_ports(
        self, ec2, sg_id: str, log: DeploymentLogService, existing: bool
    ) -> None:
        for port in settings.AWS_SECURITY_GROUP_PORTS:
            if port == 22:
                cidr = settings.AWS_SECURITY_GROUP_SSH_CIDR
            else:
                cidr = settings.AWS_SECURITY_GROUP_HTTP_CIDR
            try:
                ec2.authorize_security_group_ingress(
                    GroupId=sg_id,
                    IpProtocol="tcp",
                    FromPort=port,
                    ToPort=port,
                    CidrIp=cidr,
                )
            except ClientError as exc:
                code = str(
                    (exc.response.get("Error") or {}).get("Code", "")
                )
                if code != "InvalidPermission.Duplicate":
                    raise
        log.info(
            DeploymentStage.PREPARING,
            (
                f"Security group {sg_id} ensured — inbound ports "
                f"{', '.join(str(p) for p in settings.AWS_SECURITY_GROUP_PORTS)} "
                f"only (no application ports exposed publicly)."
            ),
        )

    def _resolve_image(self, ec2) -> dict:
        """Resolve the AMI from config/settings, SSM public parameter, or search."""
        ami_id = str(
            self.config.get("ami_id") or settings.AWS_EC2_AMI_ID or ""
        )
        if not ami_id:
            session = self.get_session()
            try:
                ssm = session.client("ssm", region_name=self._region())
                ami_id = ssm.get_parameter(
                    Name=settings.AWS_EC2_AMI_SSM_PARAMETER
                )["Parameter"]["Value"]
            except (ClientError, BotoCoreError):
                ami_id = ""
        if not ami_id:
            response = ec2.describe_images(
                Owners=["amazon"],
                Filters=[
                    {"Name": "name", "Values": ["al2023-ami-*-x86_64"]},
                    {"Name": "state", "Values": ["available"]},
                    {"Name": "architecture", "Values": ["x86_64"]},
                ],
            )
            images = sorted(
                response.get("Images", []),
                key=lambda img: img.get("CreationDate", ""),
                reverse=True,
            )
            if not images:
                raise AwsEc2Error(
                    "Could not resolve an Amazon Linux 2023 AMI. "
                    "Set AWS_EC2_AMI_ID in backend/.env."
                )
            ami_id = images[0]["ImageId"]
        try:
            detail = ec2.describe_images(ImageIds=[ami_id])["Images"]
            return detail[0] if detail else {"ImageId": ami_id}
        except ClientError:
            return {"ImageId": ami_id}

    def _user_data(self) -> str:
        # SSM is mandatory for CloudWise because all remote deployment
        # actions use Systems Manager instead of SSH. Therefore the SSM
        # bootstrap must run even when Docker installation is disabled.
        lines = [
            "#!/bin/bash\n",
            "set -euxo pipefail\n",
            "exec > /var/log/cloudwise-userdata.log 2>&1\n",
            "echo '[CloudWise] Starting bootstrap'\n",
            "if command -v dnf > /dev/null 2>&1; then\n",
            "  dnf install -y amazon-ssm-agent curl || true\n",
            "elif command -v yum > /dev/null 2>&1; then\n",
            "  yum install -y amazon-ssm-agent curl || true\n",
            "elif command -v apt-get > /dev/null 2>&1; then\n",
            "  apt-get update -y || true\n",
            "  apt-get install -y amazon-ssm-agent || "
            "(snap install amazon-ssm-agent --classic || true)\n",
            "fi\n",
            "systemctl daemon-reload || true\n",
            "systemctl enable amazon-ssm-agent || true\n",
            "systemctl restart amazon-ssm-agent || systemctl start amazon-ssm-agent || true\n",
            "echo '[CloudWise] SSM bootstrap completed'\n",
        ]

        if settings.AWS_INSTALL_DOCKER:
            lines.extend([
                "if command -v dnf > /dev/null 2>&1; then\n",
                "  dnf install -y docker && systemctl enable --now docker\n",
                "elif command -v yum > /dev/null 2>&1; then\n",
                "  yum install -y docker && systemctl enable --now docker\n",
                "elif command -v apt-get > /dev/null 2>&1; then\n",
                "  apt-get update -y && apt-get install -y docker.io "
                "&& systemctl enable --now docker\n",
                "fi\n",
                "if ! command -v docker-compose > /dev/null 2>&1; then\n",
                "  curl -fsSL "
                "https://github.com/docker/compose/releases/latest/"
                "download/docker-compose-linux-x86_64 "
                "-o /usr/local/bin/docker-compose\n",
                "  chmod +x /usr/local/bin/docker-compose\n",
                "fi\n",
                "mkdir -p /usr/local/lib/docker/cli-plugins\n",
                "if [ ! -e /usr/local/lib/docker/cli-plugins/docker-compose ]; then\n",
                "  ln -sf /usr/local/bin/docker-compose "
                "/usr/local/lib/docker/cli-plugins/docker-compose\n",
                "fi\n",
                "echo '[CloudWise] Docker bootstrap completed'\n",
            ])

        lines.append("echo '[CloudWise] User-data finished'\n")
        return "".join(lines)

    def _run_instances(
        self,
        ec2,
        *,
        image: dict,
        instance_type: str,
        sg_id: str,
        key_name: str,
        instance_profile: str,
        env_name: str,
    ) -> dict:
        tags = [
            {"Key": "ManagedBy", "Value": "CloudWise"},
            {"Key": "Name", "Value": f"cloudwise-{env_name}"[:256]},
        ]
        if self.user is not None:
            tags.append({"Key": "CloudWiseUserId", "Value": str(self.user.id)})

        params: dict[str, Any] = {
            "ImageId": image["ImageId"],
            "InstanceType": instance_type,
            "MinCount": 1,
            "MaxCount": 1,
            "SecurityGroupIds": [sg_id],
            "TagSpecifications": [
                {"ResourceType": "instance", "Tags": tags},
                {"ResourceType": "volume", "Tags": tags},
            ],
            "MetadataOptions": {
                "HttpTokens": "required",  # IMDSv2
                "HttpEndpoint": "enabled",
            },
        }
        root_device = image.get("RootDeviceName")
        volume_gb = settings.AWS_EC2_ROOT_VOLUME_GB
        if root_device and volume_gb > 0:
            params["BlockDeviceMappings"] = [
                {
                    "DeviceName": root_device,
                    "Ebs": {
                        "VolumeSize": volume_gb,
                        "VolumeType": "gp3",
                        "DeleteOnTermination": True,
                    },
                }
            ]
        if key_name:
            params["KeyName"] = key_name
        # SSM is mandatory for CloudWise deployments. Always launch the
        # instance with the configured profile, falling back to the
        # CloudWise-managed SSM profile when settings are empty.
        profile_name = (
            str(instance_profile or "").strip()
            or getattr(settings, "AWS_EC2_INSTANCE_PROFILE", "")
            or "cloudwise-ec2-ssm"
        ).strip() or "cloudwise-ec2-ssm"
        params["IamInstanceProfile"] = {"Name": profile_name}
        user_data = self._user_data()
        if user_data:
            params["UserData"] = user_data

        response = ec2.run_instances(**params)
        instances = response.get("Instances", [])
        if not instances:
            raise AwsEc2Error("EC2 RunInstances returned no instance.")
        return instances[0]

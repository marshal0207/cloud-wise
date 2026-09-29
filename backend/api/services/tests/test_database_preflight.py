"""
Tests for the database preflight / failure-classification layer.

Why it exists: CloudWise never provisions a database — the repository points
at an external one (MongoDB Atlas, Neon, RDS, ...) and a rebuilt instance
gets a new public IP, so the database's network access list stops matching.
The preflight runs on the instance before the deployment is declared healthy
and turns a bare "502" into a specific error code.

Covered here:
  * connection-string parsing — host/port/kind only, credentials never kept
  * database dependency detection (value > plan > files, None when no DB)
  * probe staging over SSM (base64 chunks, python3 runtime, cleanup)
  * marker parsing and report building (SKIPPED never fails a deployment)
  * health-failure classification into DATABASE_*/BACKEND_*/NGINX_*/FRONTEND_*
  * the optional Elastic IP step (graceful fallback, never a hard failure)
  * the optional permission check (a denied optional action never blocks)
"""

import json
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError
from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from api.models import AWSConnection
from api.services.deployment import database_preflight as pre
from api.services.deployment.aws_ec2_provider import AwsEc2Error, AwsEc2Provider
from api.services.deployment.aws_permissions import get_cloudwise_permissions_policy
from api.services.deployment.preflight import _check, summarize, verify_permissions
from api.services.tests.test_aws_ec2_provider import _make_mocks

User = get_user_model()

MONGO_URI = "mongodb+srv://admin:S3cr3t@cluster0.abc.mongodb.net/mydb?retryWrites=true"


def db_marker(**fields):
    """Build probe output exactly as the in-instance script prints it."""
    payload = " ".join(f"{key}={value}" for key, value in fields.items())
    return (
        f"CLOUDWISE_DB_PROBE {payload}\n"
        "CLOUDWISE_PROXY api=000 proxy=unknown"
    )


class ConnectionStringTests(SimpleTestCase):
    """parse_database_url keeps host/port/kind and drops everything else."""

    def test_mongodb_srv_url_is_reduced_to_host_port_kind(self):
        parsed = pre.parse_database_url(MONGO_URI)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["kind"], "mongodb")
        self.assertEqual(parsed["host"], "cluster0.abc.mongodb.net")
        self.assertEqual(parsed["port"], 27017)
        self.assertTrue(parsed["srv"])

    def test_credentials_never_survive_parsing(self):
        parsed = pre.parse_database_url(MONGO_URI) or {}
        for value in parsed.values():
            self.assertNotIn("S3cr3t", str(value))
            self.assertNotIn("admin", str(value))

    def test_first_seed_host_is_used(self):
        parsed = pre.parse_database_url(
            "mongodb://node1.example.com:27018,node2.example.com/db"
        )
        self.assertEqual(parsed["host"], "node1.example.com")
        self.assertEqual(parsed["port"], 27018)

    def test_default_port_applied_when_absent(self):
        parsed = pre.parse_database_url("postgres://db.example.com/app")
        self.assertEqual(parsed["kind"], "postgresql")
        self.assertEqual(parsed["port"], 5432)
        self.assertFalse(parsed["srv"])

    def test_unsupported_or_malformed_values_return_none(self):
        for value in (
            None,
            "",
            "not a url",
            "http://example.com",
            "mongodb://",
            "mongodb://[::1]/db",
        ):
            self.assertIsNone(pre.parse_database_url(value))


class DependencyDetectionTests(SimpleTestCase):
    """detect_database_dependency: a concrete value beats file analysis."""

    def test_database_url_value_wins(self):
        dependency = pre.detect_database_dependency(
            env_vars={"MONGO_URI": MONGO_URI, "PORT": "3000"}
        )
        self.assertEqual(dependency["kind"], "mongodb")
        self.assertEqual(dependency["envVar"], "MONGO_URI")
        self.assertEqual(dependency["source"], "uri")

    def test_plan_and_declared_variable_name_fall_back(self):
        dependency = pre.detect_database_dependency(
            env_vars={"MONGO_URI": ""},
            plan={
                "database": {"type": "MongoDB", "detected": True},
                "requiredEnvVars": ["MONGO_URI"],
            },
        )
        self.assertEqual(dependency["kind"], "mongodb")
        self.assertEqual(dependency["envVar"], "MONGO_URI")
        self.assertEqual(dependency["port"], 27017)
        self.assertEqual(dependency["source"], "analysis")
        self.assertEqual(dependency["host"], "")

    def test_postgres_plan_maps_to_postgresql_default_port(self):
        dependency = pre.detect_database_dependency(
            env_vars={},
            plan={"database": {"type": "PostgreSQL"}},
        )
        self.assertEqual(dependency["kind"], "postgresql")
        self.assertEqual(dependency["port"], 5432)

    def test_repository_without_database_returns_none(self):
        self.assertIsNone(pre.detect_database_dependency(env_vars={"PORT": "3000"}))

    def test_odd_environment_values_do_not_raise(self):
        for env_vars in ({1: None}, {"MONGO_URI": 12345}, {"MONGO_URI": {"a": 1}}):
            try:
                pre.detect_database_dependency(env_vars=env_vars)
            except Exception as exc:  # pragma: no cover
                self.fail(f"detection raised for {env_vars!r}: {exc}")


class ProbeStagingTests(SimpleTestCase):
    """The probe travels to the instance base64-encoded and is cleaned up."""

    def test_probe_source_is_available(self):
        self.assertTrue(pre.probe_source())

    def test_commands_stage_decode_run_and_remove(self):
        commands = pre.build_probe_commands(
            {"kind": "mongodb", "envVar": "MONGO_URI", "host": "h.example.com",
             "port": 27017, "srv": False},
            env_file="/opt/cloudwise/projects/p/prod/.env",
            proxy_url="http://127.0.0.1:5000/api/health",
        )
        joined = "\n".join(commands)
        self.assertIn("base64 -d", joined)
        self.assertIn("python3", joined)
        self.assertIn(pre.PROBE_PATH, joined)
        self.assertIn("rm -f", joined)
        self.assertIn("--proxy-url 'http://127.0.0.1:5000/api/health'", joined)
        # The source itself is only ever shipped base64-encoded.
        self.assertNotIn("import socket", joined)

    def test_no_source_means_no_commands(self):
        with patch.object(pre, "probe_source", return_value=""):
            self.assertEqual(
                pre.build_probe_commands(None, env_file="/tmp/.env"), []
            )

    def test_probe_url_uses_loopback_and_detected_port(self):
        self.assertEqual(
            pre.build_probe_url(5000, "/api/health"),
            "http://127.0.0.1:5000/api/health",
        )
        self.assertEqual(pre.build_probe_url(80, ""), "http://127.0.0.1/")

    def test_probe_url_refuses_unsafe_paths(self):
        self.assertEqual(
            pre.build_probe_url(5000, "/a b;rm -rf /"), "http://127.0.0.1:5000/"
        )


class MarkerParsingTests(SimpleTestCase):
    """Markers → report: conservative verdicts, no secrets, no false fails."""

    def test_no_output_is_skipped_never_failed(self):
        for output in ("", None, "   "):
            report = pre.build_preflight_report(probe_output=output)
            self.assertEqual(report["status"], pre.STATUS_SKIPPED)
            self.assertNotEqual(report["status"], pre.STATUS_FAILED)
            self.assertEqual(report["errorCode"], "")

    def test_runtime_unavailable_is_skipped(self):
        report = pre.build_preflight_report(
            probe_output="CLOUDWISE_DB_PROBE status=unavailable"
        )
        self.assertEqual(report["status"], pre.STATUS_SKIPPED)

    def test_missing_environment_variable_fails_with_specific_code(self):
        report = pre.build_preflight_report(
            dependency={"kind": "mongodb", "envVar": "MONGO_URI",
                        "host": "c.mongodb.net", "port": 27017},
            probe_output=db_marker(
                kind="mongodb", env="missing", dns="unknown", tcp="unknown",
                verdict="env_missing",
            ),
        )
        self.assertEqual(report["status"], pre.STATUS_FAILED)
        self.assertEqual(report["errorCode"], "DATABASE_ENV_MISSING")
        self.assertIn("MONGO_URI", report["message"])

    def test_unreachable_database_fails_with_connection_code(self):
        report = pre.build_preflight_report(
            dependency={"kind": "mongodb", "envVar": "MONGO_URI",
                        "host": "c.mongodb.net", "port": 27017},
            probe_output=db_marker(
                kind="mongodb", env="ok", dns="fail", tcp="unknown",
                verdict="unreachable",
            ),
            public_ip="13.232.1.10",
        )
        self.assertEqual(report["status"], pre.STATUS_FAILED)
        self.assertEqual(report["errorCode"], "DATABASE_CONNECTION_FAILED")
        self.assertIn("13.232.1.10", report["message"])
        self.assertIn("network access list", report["message"])
        self.assertIn("0.0.0.0/0", report["message"])

    def test_reachable_database_is_success(self):
        report = pre.build_preflight_report(
            dependency={"kind": "mongodb", "envVar": "MONGO_URI",
                        "host": "c.mongodb.net", "port": 27017},
            probe_output=db_marker(
                kind="mongodb", env="ok", dns="ok", tcp="ok",
                verdict="reachable",
            ),
        )
        self.assertEqual(report["status"], pre.STATUS_SUCCESS)
        self.assertEqual(report["errorCode"], "")
        self.assertIn("reachable", report["message"])

    def test_repository_without_database_is_not_applicable(self):
        report = pre.build_preflight_report(
            probe_output=db_marker(
                kind="none", env="unknown", dns="unknown", tcp="unknown",
                verdict="not_applicable",
            ),
        )
        self.assertEqual(report["status"], pre.STATUS_SUCCESS)
        self.assertIn("No external database", report["message"])

    def test_proxy_marker_is_captured(self):
        report = pre.build_preflight_report(
            dependency={"kind": "mongodb", "envVar": "MONGO_URI"},
            probe_output=(
                "CLOUDWISE_DB_PROBE kind=mongodb env=ok dns=ok tcp=ok "
                "verdict=reachable\n"
                "CLOUDWISE_PROXY api=502 proxy=nginx"
            ),
        )
        self.assertEqual(report["proxy"]["statusCode"], 502)
        self.assertEqual(report["proxy"]["origin"], "nginx")
        self.assertIn("502", report["message"])

    def test_reports_never_contain_connection_string_material(self):
        report = pre.build_preflight_report(
            dependency={"kind": "mongodb", "envVar": "MONGO_URI",
                        "host": "c.mongodb.net", "port": 27017},
            probe_output=db_marker(
                kind="mongodb", env="missing", dns="unknown", tcp="unknown",
                verdict="env_missing",
            ),
        )
        blob = json.dumps(report)
        self.assertNotIn("S3cr3t", blob)
        self.assertNotIn("mongodb+srv://", blob)


class ClassificationTests(SimpleTestCase):
    """A failed health check must be told apart from a database failure."""

    def test_failed_preflight_wins_over_everything(self):
        code, message = pre.classify_health_failure(
            health_message="HTTP 502 from 127.0.0.1:5000",
            split_report={"status": "FAILED"},
            preflight={
                "status": pre.STATUS_FAILED,
                "errorCode": "DATABASE_ENV_MISSING",
                "message": "Database preflight failed: environment variable "
                           "MONGO_URI is missing.",
            },
            app_port=5000,
        )
        self.assertEqual(code, "DATABASE_ENV_MISSING")
        self.assertIn("MONGO_URI", message)

    def test_nginx_upstream_502_is_backend_not_running(self):
        code, _ = pre.classify_health_failure(
            health_message="HTTP 502 from 127.0.0.1:80",
            split_report={
                "status": "FAILED",
                "backend": {"statusCode": 502, "ok": False},
                "frontend": {"ok": True, "statusCode": 200},
            },
            preflight={"status": pre.STATUS_SUCCESS, "proxy": {"origin": "nginx"}},
            app_port=80,
        )
        self.assertEqual(code, pre.ERROR_BACKEND_NOT_RUNNING)

    def test_backend_5xx_is_not_blamed_on_the_backend(self):
        code, message = pre.classify_health_failure(
            health_message="HTTP 502 from 127.0.0.1:5000",
            split_report={
                "status": "FAILED",
                "backend": {"statusCode": 502, "ok": False},
                "frontend": {"ok": True, "statusCode": 200},
            },
            preflight={"status": pre.STATUS_SUCCESS, "proxy": {"origin": "app"}},
            app_port=5000,
        )
        self.assertEqual(code, "")
        self.assertEqual(message, "")

    def test_dead_router_is_nginx_proxy_failed(self):
        code, _ = pre.classify_health_failure(
            health_message="HTTP 000 from 127.0.0.1:80",
            split_report={
                "status": "FAILED",
                "backend": {"statusCode": 0, "ok": False},
                "frontend": {"ok": False, "statusCode": 0},
            },
            preflight={"status": pre.STATUS_SUCCESS},
            app_port=80,
        )
        self.assertEqual(code, pre.ERROR_NGINX_PROXY_FAILED)

    def test_dead_frontend_is_frontend_failed(self):
        code, _ = pre.classify_health_failure(
            health_message="HTTP 404 from 127.0.0.1:80",
            split_report={
                "status": "FAILED",
                "backend": {"statusCode": 200, "ok": True},
                "frontend": {"ok": False, "statusCode": 404},
            },
            preflight={"status": pre.STATUS_SUCCESS},
            app_port=80,
        )
        self.assertEqual(code, pre.ERROR_FRONTEND_FAILED)

    def test_skipped_split_report_does_not_drive_the_diagnosis(self):
        """A SKIPPED split report (mocked SSM) must not mean 'nginx is dead'."""
        code, _ = pre.classify_health_failure(
            health_message="HTTP 000 from 127.0.0.1:5000",
            split_report={"status": "SKIPPED", "backend": {"statusCode": None}},
            preflight={"status": pre.STATUS_SKIPPED},
            app_port=5000,
        )
        self.assertEqual(code, pre.ERROR_BACKEND_NOT_RUNNING)

    def test_untouched_health_messages_keep_generic_failure(self):
        code, message = pre.classify_health_failure(
            health_message="Instance health probe SSM status Failed: no output",
            split_report={"status": "SKIPPED"},
            preflight={"status": pre.STATUS_SKIPPED},
            app_port=5000,
        )
        self.assertEqual(code, "")
        self.assertEqual(message, "")

    def test_http_504_is_backend_not_running(self):
        code, _ = pre.classify_health_failure(
            health_message="HTTP 504 from 127.0.0.1:5000",
            app_port=5000,
        )
        self.assertEqual(code, pre.ERROR_BACKEND_NOT_RUNNING)

    def test_refused_on_port_80_is_nginx_proxy_failed(self):
        code, _ = pre.classify_health_failure(
            health_message="Health check failed for http://127.0.0.1/: "
                           "connection refused",
            app_port=80,
        )
        self.assertEqual(code, pre.ERROR_NGINX_PROXY_FAILED)

    def test_closed_application_port_is_backend_not_running(self):
        code, _ = pre.classify_health_failure(
            health_message="Health check failed for http://127.0.0.1:5000/: "
                           "connection refused",
            app_port=5000,
        )
        self.assertEqual(code, pre.ERROR_BACKEND_NOT_RUNNING)

    def test_empty_message_yields_no_diagnosis(self):
        code, message = pre.classify_health_failure(health_message="", app_port=5000)
        self.assertEqual(code, "")
        self.assertEqual(message, "")

    def test_error_codes_are_distinct_and_stable(self):
        codes = {
            pre.ERROR_DATABASE_ENV_MISSING,
            pre.ERROR_DATABASE_CONNECTION_FAILED,
            pre.ERROR_BACKEND_NOT_RUNNING,
            pre.ERROR_NGINX_PROXY_FAILED,
            pre.ERROR_FRONTEND_FAILED,
        }
        self.assertEqual(len(codes), 5)
        self.assertTrue(all(code.isupper() for code in codes))


class ContainerStateMarkerTests(SimpleTestCase):
    """Machine-readable container state must drive the diagnosis."""

    ATLAS = {"configured": False, "atlas": True, "host": "c0.abc.mongodb.net"}
    SPLIT_FAILED = {
        "status": "FAILED",
        "backend": {"statusCode": 502, "ok": False},
        "frontend": {"ok": True, "statusCode": 200},
    }

    def test_exited_marker_is_reported_as_a_failed_container(self):
        code, message = pre.classify_health_failure(
            health_message="Split health check failed: backend HTTP 502",
            split_report=self.SPLIT_FAILED,
            diagnostics=(
                "CLOUDWISE_CONTAINER service=nginx status=running "
                "restarts=0 exit=0\n"
                "CLOUDWISE_CONTAINER service=backend status=exited "
                "restarts=1 exit=1\n"
            ),
        )
        self.assertEqual(code, pre.ERROR_CONTAINER_FAILED)
        self.assertIn("backend", message)
        self.assertIn("exited", message)
        self.assertIn("exit", message)

    def test_a_clean_one_shot_exit_is_not_a_failure(self):
        diagnostics = (
            "CLOUDWISE_CONTAINER service=migrations status=exited "
            "restarts=0 exit=0\n"
        )
        self.assertIsNone(pre._stopped_container(diagnostics))

    def test_restart_counter_reads_as_a_crash_loop(self):
        diagnostics = (
            "CLOUDWISE_CONTAINER service=backend status=running "
            "restarts=7 exit=1\n"
        )
        self.assertEqual(
            pre._crash_looping_container(diagnostics), ("backend", 7)
        )

    def test_crash_loop_with_a_database_error_reports_the_root_cause(self):
        code, message = pre.classify_health_failure(
            health_message="Split health check failed: backend HTTP 502",
            split_report=self.SPLIT_FAILED,
            diagnostics=(
                "CLOUDWISE_CONTAINER service=backend status=running "
                "restarts=5 exit=1\n"
                "MongooseServerSelectionError: Could not connect to any "
                "servers in your MongoDB Atlas cluster (ReplicaSetNoPrimary)\n"
            ),
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
        )
        self.assertEqual(code, pre.ERROR_MONGODB_ATLAS_NOT_CONFIGURED)
        self.assertIn("restarted 5 times", message)
        self.assertIn("203.0.113.10/32", message)

    def test_crash_loop_without_a_database_error_names_the_container(self):
        code, message = pre.classify_health_failure(
            health_message="Split health check failed: backend HTTP 502",
            split_report=self.SPLIT_FAILED,
            diagnostics=(
                "CLOUDWISE_CONTAINER service=backend status=running "
                "restarts=4 exit=137\n"
            ),
        )
        self.assertEqual(code, pre.ERROR_CONTAINER_FAILED)
        self.assertIn("restarted 4 times", message)

    def test_healthy_markers_do_not_invent_a_container_failure(self):
        code, message = pre.classify_health_failure(
            health_message="Split health check failed: backend HTTP 502",
            split_report=self.SPLIT_FAILED,
            diagnostics=(
                "CLOUDWISE_CONTAINER service=backend status=running "
                "restarts=0 exit=0\n"
                "CLOUDWISE_CONTAINER service=frontend status=running "
                "restarts=0 exit=0\n"
            ),
        )
        # The backend answered 502 while nginx was in front of it: the
        # container itself is fine, so the "not answering" diagnosis stands.
        self.assertEqual(code, pre.ERROR_BACKEND_NOT_RUNNING)


class BackendStartFailureTests(SimpleTestCase):
    """The gate runs before any HTTP probe exists — logs are the evidence."""

    ATLAS = {"configured": False, "atlas": True, "host": "c0.abc.mongodb.net"}

    def test_blocked_atlas_is_reported_with_the_instance_address(self):
        code, message = pre.classify_backend_start_failure(
            "CLOUDWISE_GATE_RESULT crashloop\n"
            "CLOUDWISE_CONTAINER service=backend status=running "
            "restarts=3 exit=1\n"
            "MongooseServerSelectionError: Could not connect to any servers "
            "in your MongoDB Atlas cluster (ReplicaSetNoPrimary)\n",
            atlas=self.ATLAS,
            public_ip="54.226.154.68",
            backend_port=5000,
        )
        self.assertEqual(code, pre.ERROR_MONGODB_ATLAS_NOT_CONFIGURED)
        self.assertIn("54.226.154.68/32", message)
        self.assertIn("never 0.0.0.0/0", message)

    def test_rejected_credentials_are_reported_as_authentication(self):
        code, message = pre.classify_backend_start_failure(
            "CLOUDWISE_GATE_RESULT crashloop\n"
            "MongooseServerSelectionError: Authentication failed\n",
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
            backend_port=5000,
        )
        self.assertEqual(code, pre.ERROR_DATABASE_AUTH_FAILED)
        self.assertIn("authentication", message.lower())

    def test_dead_container_is_reported_without_a_database_claim(self):
        code, message = pre.classify_backend_start_failure(
            "CLOUDWISE_GATE_RESULT exited\n"
            "CLOUDWISE_CONTAINER service=backend status=exited "
            "restarts=1 exit=1\n"
            "Error: Cannot find module './missing.js'\n",
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
            backend_port=5000,
        )
        self.assertEqual(code, pre.ERROR_CONTAINER_FAILED)
        self.assertIn("backend", message)
        self.assertIn("exited", message)

    def test_a_slow_start_produces_no_diagnosis(self):
        code, message = pre.classify_backend_start_failure(
            "CLOUDWISE_GATE_RESULT starting\n"
            "CLOUDWISE_CONTAINER service=backend status=running "
            "restarts=0 exit=0\n",
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
            backend_port=5000,
        )
        self.assertEqual(code, "")
        self.assertEqual(message, "")

    def test_a_listening_backend_produces_no_diagnosis(self):
        self.assertEqual(
            pre.classify_backend_start_failure(
                "CLOUDWISE_GATE_RESULT listening\n", backend_port=5000
            ),
            ("", ""),
        )

    def test_gate_verdict_is_read_from_the_marker(self):
        self.assertEqual(pre.gate_result("x\nCLOUDWISE_GATE_RESULT listening"), "listening")
        self.assertEqual(pre.gate_result(""), "")


class ProxyOriginTests(SimpleTestCase):
    """A 502 page from nginx must not be read as the application answering."""

    def test_nginx_version_footer_is_recognised(self):
        from api.services.deployment import database_probe

        result = database_probe.check_proxy(
            "http://127.0.0.1/api/health",
            fetch=lambda _url, _timeout: (
                502,
                "<html><head><title>502 Bad Gateway</title></head>"
                "<body><center><h1>502 Bad Gateway</h1></center>"
                "<center>nginx/1.31.6</center></body></html>",
            ),
        )
        self.assertEqual(result["api"], 502)
        self.assertEqual(result["proxy"], "nginx")

    def test_application_body_is_still_the_application(self):
        from api.services.deployment import database_probe

        result = database_probe.check_proxy(
            "http://127.0.0.1/api/health",
            fetch=lambda _url, _timeout: (503, '{"database":"unavailable"}'),
        )
        self.assertEqual(result["proxy"], "app")


class AwsEc2ErrorTests(SimpleTestCase):
    def test_error_code_defaults_to_empty_string(self):
        self.assertEqual(AwsEc2Error("boom").error_code, "")

    def test_error_code_is_carried_for_the_pipeline(self):
        exc = AwsEc2Error("boom", error_code=pre.ERROR_DATABASE_CONNECTION_FAILED)
        self.assertEqual(exc.error_code, "DATABASE_CONNECTION_FAILED")
        self.assertEqual(str(exc), "boom")


class ElasticIpTests(SimpleTestCase):
    """The optional stable-address step must never break a deployment."""

    def _provider(self, **config):
        return AwsEc2Provider(config=config)

    def test_disabled_by_config_skips_the_api_entirely(self):
        ec2 = MagicMock()
        log = MagicMock()
        ip = self._provider(use_elastic_ip=False)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "")
        ec2.describe_addresses.assert_not_called()
        ec2.allocate_address.assert_not_called()

    def test_address_already_attached_is_reused(self):
        ec2 = MagicMock()
        ec2.describe_addresses.return_value = {
            "Addresses": [{"PublicIp": "52.1.1.1", "InstanceId": "i-1"}]
        }
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "52.1.1.1")
        ec2.allocate_address.assert_not_called()

    def test_free_cloudwise_address_is_reused_before_allocating(self):
        ec2 = MagicMock()
        ec2.describe_addresses.side_effect = [
            {"Addresses": []},
            {
                "Addresses": [
                    {
                        "PublicIp": "52.2.2.2",
                        "AllocationId": "eipalloc-9",
                        "InstanceId": None,
                        "Tags": [{"Key": "ManagedBy", "Value": "CloudWise"}],
                    }
                ]
            },
        ]
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "52.2.2.2")
        ec2.associate_address.assert_called_once_with(
            AllocationId="eipalloc-9", InstanceId="i-1"
        )
        ec2.allocate_address.assert_not_called()

    def test_new_allocation_is_tagged_and_associated(self):
        ec2 = MagicMock()
        ec2.describe_addresses.return_value = {"Addresses": []}
        ec2.allocate_address.return_value = {
            "PublicIp": "52.3.3.3",
            "AllocationId": "eipalloc-1",
        }
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "52.3.3.3")
        ec2.create_tags.assert_called_once()
        ec2.associate_address.assert_called_once_with(
            AllocationId="eipalloc-1", InstanceId="i-1"
        )
        ec2.release_address.assert_not_called()

    def test_association_failure_releases_the_address_and_falls_back(self):
        ec2 = MagicMock()
        ec2.describe_addresses.return_value = {"Addresses": []}
        ec2.allocate_address.return_value = {
            "PublicIp": "52.4.4.4",
            "AllocationId": "eipalloc-2",
        }
        ec2.associate_address.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
            "AssociateAddress",
        )
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "")
        ec2.release_address.assert_called_once_with(AllocationId="eipalloc-2")
        log.warning.assert_called_once()

    def test_missing_iam_permission_is_a_warning_not_a_failure(self):
        ec2 = MagicMock()
        ec2.describe_addresses.side_effect = ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "denied"}},
            "DescribeAddresses",
        )
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "")
        ec2.allocate_address.assert_not_called()
        self.assertIn("dynamic public IP", str(log.warning.call_args[0][1]))

    def test_unusable_api_response_falls_back(self):
        ec2 = MagicMock()
        ec2.describe_addresses.return_value = {}
        ec2.allocate_address.return_value = MagicMock()
        log = MagicMock()
        ip = self._provider(use_elastic_ip=True)._ensure_elastic_ip(
            ec2, "i-1", log
        )
        self.assertEqual(ip, "")

    def test_invalid_ip_values_are_rejected(self):
        self.assertTrue(AwsEc2Provider._is_ipv4("52.1.2.3"))
        self.assertFalse(AwsEc2Provider._is_ipv4(""))
        self.assertFalse(AwsEc2Provider._is_ipv4("<MagicMock id=1>"))
        self.assertFalse(AwsEc2Provider._is_ipv4("999.1.1.1"))


class PreflightHelperTests(SimpleTestCase):
    """_run_database_preflight: reporting only, never a deployment failure."""

    def _provider(self):
        return AwsEc2Provider(
            config={
                "files": {"package.json": "{}"},
                "env_vars": {"MONGO_URI": ""},
                "deployment_plan": {
                    "database": {"type": "MongoDB", "detected": True},
                    "requiredEnvVars": ["MONGO_URI"],
                    "apiProbePaths": ["/api/health"],
                },
            }
        )

    def test_mocked_ssm_is_reported_as_skipped(self):
        ssm = MagicMock()
        ssm.send_command.return_value = {}
        report = self._provider()._run_database_preflight(
            ssm, "i-1", "/opt/cloudwise/projects/p/prod", MagicMock(),
            app_port=5000, public_ip="13.232.1.10",
        )
        self.assertEqual(report["status"], pre.STATUS_SKIPPED)
        self.assertEqual(report["errorCode"], "")

    def test_probe_markers_produce_a_failed_report(self):
        ssm = MagicMock()
        ssm.send_command.return_value = {"Command": {"CommandId": "c-1"}}
        ssm.get_command_invocation.return_value = {
            "Status": "Success",
            "StandardOutputContent": db_marker(
                kind="mongodb", env="ok", dns="fail", tcp="unknown",
                verdict="unreachable",
            ),
        }
        report = self._provider()._run_database_preflight(
            ssm, "i-1", "/opt/cloudwise/projects/p/prod", MagicMock(),
            app_port=5000, public_ip="13.232.1.10",
        )
        self.assertEqual(report["status"], pre.STATUS_FAILED)
        self.assertEqual(report["errorCode"], "DATABASE_CONNECTION_FAILED")

    def test_ssm_failure_is_reported_as_skipped(self):
        ssm = MagicMock()
        ssm.send_command.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}},
            "SendCommand",
        )
        report = self._provider()._run_database_preflight(
            ssm, "i-1", "/opt/cloudwise/projects/p/prod", MagicMock(),
            app_port=5000,
        )
        self.assertEqual(report["status"], pre.STATUS_SKIPPED)

    def test_probe_command_batch_is_produced_for_a_mongo_repository(self):
        commands = pre.build_probe_commands(
            {"kind": "mongodb", "envVar": "MONGO_URI", "host": "",
             "port": 27017, "srv": False},
            env_file="/opt/cloudwise/projects/p/prod/.env",
            proxy_url=pre.build_probe_url(5000, "/api/health"),
        )
        self.assertGreater(len(commands), 3)
        self.assertTrue(all(isinstance(command, str) for command in commands))


class OptionalPermissionCheckTests(SimpleTestCase):
    """A denied optional action must never block a deployment."""

    @staticmethod
    def _denied():
        raise ClientError(
            {"Error": {"Code": "UnauthorizedOperation", "Message": "no"}},
            "DescribeAddresses",
        )

    def test_optional_denied_check_does_not_block(self):
        check = _check(
            "elastic_ip",
            "Stable public IP (Elastic IP)",
            "ec2:DescribeAddresses",
            self._denied,
            critical=False,
            optional=True,
        )
        self.assertIsNone(check["ok"])
        self.assertFalse(check["critical"])
        self.assertEqual(summarize([check]), (True, []))

    def test_required_denied_check_still_blocks(self):
        check = _check(
            "sts",
            "STS AssumeRole",
            "sts:GetCallerIdentity",
            self._denied,
        )
        self.assertFalse(check["ok"])
        self.assertEqual(summarize([check]), (False, ["sts:GetCallerIdentity"]))

    def test_policy_grants_the_elastic_ip_actions(self):
        actions = set()
        for statement in get_cloudwise_permissions_policy():
            action = statement.get("Action")
            actions.update(
                [action] if isinstance(action, str) else list(action or [])
            )
        for expected in (
            "ec2:DescribeAddresses",
            "ec2:AllocateAddress",
            "ec2:AssociateAddress",
            "ec2:DisassociateAddress",
            "ec2:ReleaseAddress",
        ):
            self.assertIn(expected, actions)

    @patch("api.services.deployment.preflight.boto3.Session")
    def test_elastic_ip_check_follows_the_setting(self, session_cls):
        session_cls.return_value.client.return_value = MagicMock()
        credentials = {
            "aws_access_key_id": "AKIAEXAMPLE",
            "aws_secret_access_key": "example",
        }
        with override_settings(AWS_USE_ELASTIC_IP=True):
            keys = {
                check["key"]
                for check in verify_permissions(
                    None, credentials=credentials, region="us-east-1"
                )
            }
            self.assertIn("elastic_ip", keys)
        with override_settings(AWS_USE_ELASTIC_IP=False):
            keys = {
                check["key"]
                for check in verify_permissions(
                    None, credentials=credentials, region="us-east-1"
                )
            }
            self.assertNotIn("elastic_ip", keys)


class ProvisionElasticIpTests(TestCase):
    """provision() uses the stable address as the instance public IP."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="eipuser", password="pass1234", email="eip@example.com"
        )
        self.connection = AWSConnection.objects.create(
            user=self.user,
            role_arn="arn:aws:iam::999988887777:role/CloudWiseDeployRole",
            external_id="cloudwise-user-eip",
            account_id="999988887777",
            region="ap-south-1",
            status="active",
        )

    def _provider(self, **config):
        return AwsEc2Provider(
            user=self.user, connection=self.connection, config=config
        )

    @staticmethod
    def _provision(provider, session):
        with patch.object(provider, "get_session", return_value=session), patch.object(
            AwsEc2Provider, "_ensure_instance_profile"
        ), patch.object(AwsEc2Provider, "_ensure_ssm_managed"):
            return provider.start(
                {"environment_name": "prod", "provider": "AWS"}
            )

    @override_settings(AWS_INSTALL_DOCKER=False, AWS_USE_ELASTIC_IP=True)
    def test_new_instance_uses_the_associated_elastic_ip(self):
        session, ec2, _ssm = _make_mocks()
        ec2.describe_addresses.side_effect = [
            {"Addresses": []},
            {"Addresses": []},
        ]
        ec2.allocate_address.return_value = {
            "PublicIp": "52.7.7.7",
            "AllocationId": "eipalloc-7",
        }

        result = self._provision(self._provider(force_new_instance=True), session)

        self.assertEqual(result["public_ip"], "52.7.7.7")
        self.assertEqual(result["elastic_ip"], "52.7.7.7")
        ec2.associate_address.assert_called_once_with(
            AllocationId="eipalloc-7", InstanceId="i-0abc123"
        )
        ec2.create_tags.assert_any_call(
            Resources=["eipalloc-7"],
            Tags=[
                {"Key": "ManagedBy", "Value": "CloudWise"},
                {"Key": "Owner", "Value": str(self.user.id)},
            ],
        )

    @override_settings(AWS_INSTALL_DOCKER=False, AWS_USE_ELASTIC_IP=True)
    def test_missing_eip_permission_falls_back_to_dynamic_ip(self):
        session, ec2, _ssm = _make_mocks()
        ec2.describe_addresses.side_effect = ClientError(
            {
                "Error": {
                    "Code": "UnauthorizedOperation",
                    "Message": "not authorized",
                }
            },
            "DescribeAddresses",
        )

        result = self._provision(self._provider(force_new_instance=True), session)

        self.assertEqual(result["public_ip"], "13.232.1.10")
        self.assertEqual(result["elastic_ip"], "")
        ec2.allocate_address.assert_not_called()

    @override_settings(AWS_INSTALL_DOCKER=False, AWS_USE_ELASTIC_IP=False)
    def test_setting_disabled_keeps_the_dynamic_ip(self):
        session, ec2, _ssm = _make_mocks()

        result = self._provision(self._provider(force_new_instance=True), session)

        self.assertEqual(result["public_ip"], "13.232.1.10")
        self.assertEqual(result["elastic_ip"], "")
        ec2.describe_addresses.assert_not_called()

"""
Tests for MongoDB Atlas allowlisting, the database readiness endpoint,
nginx upstream stability and compose environment wiring.

Everything here runs without AWS, Atlas or an instance: the Atlas Admin API
is stubbed at the ``_request`` seam and the instance-side commands are never
executed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from api.services.deployment import mongodb_atlas_service as atlas
from api.services.deployment.adapters import separate_frontend_backend_adapter as adapter
from api.services.deployment.database_preflight import (
    ERROR_BACKEND_NOT_RUNNING,
    ERROR_CONTAINER_FAILED,
    ERROR_DATABASE_AUTH_FAILED,
    ERROR_DOCKER_UNAVAILABLE,
    ERROR_EC2_UNAVAILABLE,
    ERROR_FRONTEND_FAILED,
    ERROR_HEALTH_ENDPOINT_FAILED,
    ERROR_MONGODB_ATLAS_NETWORK_BLOCKED,
    ERROR_MONGODB_ATLAS_NOT_CONFIGURED,
    ERROR_NGINX_PROXY_FAILED,
    STATUS_FAILED,
    STATUS_SUCCESS,
    atlas_blocked_message,
    classify_health_failure,
)
from api.services.deployment.aws_ec2_provider import AwsEc2Provider

ATLAS_URI = (
    "mongodb+srv://appuser:s3cr3t@cluster0.ab12c.mongodb.net/"
    "hospital?retryWrites=true&w=majority"
)
SAFE_KEYS = ("s3cr3t", "appuser", "mongodb+srv://")


def _assert_no_secret(test: SimpleTestCase, payload: object) -> None:
    text = repr(payload)
    for secret in SAFE_KEYS:
        test.assertNotIn(secret, text)


@override_settings(
    MONGODB_ATLAS_PUBLIC_KEY="cw-public-key",
    MONGODB_ATLAS_PRIVATE_KEY="cw-private-key",
    MONGODB_ATLAS_PROJECT_ID="64f000000000000000000001",
    MONGODB_ATLAS_AUTO_ALLOWLIST=True,
)
class UriInspectionTests(SimpleTestCase):
    def test_srv_atlas_uri_is_detected_without_keeping_credentials(self):
        info = atlas.inspect_connection_uri(ATLAS_URI)
        self.assertTrue(info["detected"])
        self.assertTrue(info["atlas"])
        self.assertTrue(info["srv"])
        self.assertTrue(info["hasDatabaseName"])
        _assert_no_secret(self, info)

    def test_plain_mongodb_uri_reports_host_and_port(self):
        info = atlas.inspect_connection_uri(
            "mongodb://user:pass@db.internal.example:27017/app"
        )
        self.assertTrue(info["detected"])
        self.assertFalse(info["atlas"])
        self.assertEqual(info["host"], "db.internal.example")
        self.assertEqual(info["port"], 27017)
        _assert_no_secret(self, info)

    def test_non_database_value_is_not_detected(self):
        info = atlas.inspect_connection_uri("https://example.com/health")
        self.assertFalse(info["detected"])
        self.assertFalse(info["atlas"])

    def test_atlas_host_helper(self):
        self.assertTrue(atlas.is_atlas_host("cluster0.abc.mongodb.net"))
        self.assertFalse(atlas.is_atlas_host("db.example.com"))
        self.assertFalse(atlas.is_atlas_host(""))

    def test_variable_name_is_found_from_a_value_then_a_name(self):
        self.assertEqual(
            atlas.find_database_env_var({"MONGODB_URI": ATLAS_URI}),
            "MONGODB_URI",
        )
        self.assertEqual(
            atlas.find_database_env_var({"MONGO_URI": ""}),
            "MONGO_URI",
        )
        self.assertEqual(
            atlas.find_database_env_var({}, files={"backend/server.js":
                                                   "const u = process.env.MONGO_URI"}),
            "MONGO_URI",
        )
        self.assertEqual(atlas.find_database_env_var({}), "")

    def test_status_never_exposes_the_private_key(self):
        status = atlas.atlas_status()
        self.assertTrue(status["configured"])
        _assert_no_secret(self, status)


# Hermetic: a developer's local backend/.env may legitimately contain
# MONGODB_ATLAS_* — "not configured" must be forced, never inherited.
@override_settings(
    MONGODB_ATLAS_PUBLIC_KEY="",
    MONGODB_ATLAS_PRIVATE_KEY="",
    MONGODB_ATLAS_PROJECT_ID="",
)
class NotConfiguredTests(SimpleTestCase):
    def test_not_configured_never_claims_allowlisting_happened(self):
        report = atlas.ensure_atlas_access_entry(
            public_ip="203.0.113.10", deployment_id="dep-1"
        )
        self.assertFalse(report["configured"])
        self.assertEqual(report["action"], "skipped")
        self.assertEqual(report["reason"], "not_configured")
        self.assertIn("MONGODB_ATLAS_PUBLIC_KEY", report["message"])
        _assert_no_secret(self, report)

    def test_missing_public_ip_skips_cleanly(self):
        report = atlas.ensure_atlas_access_entry(
            public_ip="", deployment_id="dep-1"
        )
        self.assertEqual(report["action"], "skipped")
        self.assertEqual(report["reason"], "no_public_ip")
        self.assertEqual(report["cidr"], "")


@override_settings(
    MONGODB_ATLAS_PUBLIC_KEY="pk",
    MONGODB_ATLAS_PRIVATE_KEY="sk",
    MONGODB_ATLAS_PROJECT_ID="64f000000000000000000001",
)
class AllowlistEntryTests(SimpleTestCase):
    def test_existing_entry_is_reused_not_duplicated(self):
        with patch.object(
            atlas,
            "_request",
            return_value=(
                200,
                {
                    "results": [
                        {
                            "cidrBlock": "198.51.100.4/32",
                            "comment": "CloudWise deployment dep-1",
                        }
                    ]
                },
            ),
        ) as request:
            report = atlas.ensure_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-1"
            )
        self.assertEqual(report["action"], "exists")
        self.assertEqual(report["cidr"], "198.51.100.4/32")
        # A single GET — no POST, so no duplicate entry is created.
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args[0][0], "GET")

    def test_new_entry_is_posted_as_a_narrow_slash32(self):
        responses = [
            (200, {"results": []}),
            (201, {}),
        ]
        with patch.object(atlas, "_request", side_effect=responses) as request:
            report = atlas.ensure_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-42"
            )
        self.assertEqual(report["action"], "added")
        method, path = request.call_args[0]
        body = (request.call_args[1] or {}).get("body")
        self.assertEqual(method, "POST")
        self.assertIn("/accessList", path)
        self.assertEqual(
            body, [{"cidrBlock": "198.51.100.4/32",
                    "comment": "CloudWise deployment dep-42"}]
        )
        _assert_no_secret(self, report)

    def test_duplicate_answer_from_atlas_counts_as_exists(self):
        responses = [(200, {"results": []}), (409, {"detail": "duplicate"})]
        with patch.object(atlas, "_request", side_effect=responses):
            report = atlas.ensure_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-1"
            )
        self.assertEqual(report["action"], "exists")

    def test_api_failure_is_reported_as_failed_with_the_address(self):
        responses = [
            (200, {"results": []}),
            (401, {"detail": "Unauthorized"}),
        ]
        with patch.object(atlas, "_request", side_effect=responses):
            report = atlas.ensure_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-1"
            )
        self.assertEqual(report["action"], "failed")
        self.assertIn("198.51.100.4/32", report["message"])
        self.assertNotIn("0.0.0.0/0", report["message"].replace("never 0.0.0.0/0", ""))

    def test_foreign_entries_are_never_removed(self):
        with patch.object(
            atlas,
            "_request",
            return_value=(
                200,
                {
                    "results": [
                        {"cidrBlock": "198.51.100.4/32", "comment": "office vpn"}
                    ]
                },
            ),
        ) as request:
            report = atlas.remove_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-1"
            )
        self.assertEqual(report["action"], "kept")
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args[0][0], "GET")

    def test_cloudwise_entry_is_removed_on_termination(self):
        responses = [
            (
                200,
                {
                    "results": [
                        {
                            "cidrBlock": "198.51.100.4/32",
                            "comment": "CloudWise deployment dep-1",
                        }
                    ]
                },
            ),
            (204, {}),
        ]
        with patch.object(atlas, "_request", side_effect=responses) as request:
            report = atlas.remove_atlas_access_entry(
                public_ip="198.51.100.4", deployment_id="dep-1"
            )
        self.assertEqual(report["action"], "removed")
        self.assertEqual(request.call_args[0][0], "DELETE")
        self.assertIn("198.51.100.4%2F32", request.call_args[0][1])

    def test_private_key_never_leaves_the_transport(self):
        """The key pair only ever lives inside the digest auth object."""
        from requests.auth import HTTPDigestAuth

        captured = {}

        def fake_request(method, url, **kwargs):
            captured["auth"] = kwargs.get("auth")
            captured["headers"] = kwargs.get("headers")

            class _Response:
                status_code = 200
                content = b'{"results": []}'

                def json(self):
                    return {"results": []}

            return _Response()

        with patch.object(atlas.requests, "request", fake_request):
            status, payload = atlas._request("GET", "/groups/x/accessList")

        self.assertEqual(status, 200)
        auth = captured["auth"]
        self.assertIsInstance(auth, HTTPDigestAuth)
        self.assertEqual(auth.username, "pk")
        self.assertEqual(auth.password, "sk")
        # no Authorization header is ever assembled by this module
        self.assertNotIn("Authorization", captured["headers"] or {})
        self.assertNotIn("sk", repr(payload))
        self.assertNotIn("sk", repr(captured["headers"]))


class HealthEndpointTests(SimpleTestCase):
    SERVER_JS = """const express = require('express')
const mongoose = require('mongoose')
const app = express()
app.get('/api/v1/doctors', (req, res) => res.json([]))
app.listen(5000, () => console.log('ready'))
"""

    def test_injects_a_database_gated_handler_before_listen(self):
        patched, status = adapter.install_database_health_route(
            self.SERVER_JS, app_var="app", driver="mongoose"
        )
        self.assertEqual(status, "injected")
        self.assertLess(
            patched.index("/api/health"), patched.index("app.listen")
        )
        self.assertIn("readyState === 1", patched)
        self.assertIn("database: 'unavailable'", patched)
        self.assertIn("503", patched)
        self.assertIn("200", patched)

    def test_injected_snippet_never_contains_a_connection_string(self):
        patched, _ = adapter.install_database_health_route(
            self.SERVER_JS, app_var="app", driver="mongoose",
            env_var="MONGO_URI",
        )
        for secret in SAFE_KEYS:
            self.assertNotIn(secret, patched)
        self.assertNotIn("mongodb://", patched)
        self.assertNotIn("mongodb+srv://", patched)

    def test_existing_database_aware_route_is_left_alone(self):
        source = (
            "const app = express()\n"
            "app.get('/api/health', (req, res) => res.json({"
            "ready: require('mongoose').connection.readyState === 1 }))\n"
            "app.listen(3000)\n"
        )
        patched, status = adapter.install_database_health_route(
            source, app_var="app", driver="mongoose"
        )
        self.assertEqual(status, "already_present")
        self.assertEqual(patched, source)

    def test_naive_existing_route_is_replaced_by_the_gated_one(self):
        source = (
            "const app = express()\n"
            "app.get('/api/health', (req, res) => res.json({ ok: true }))\n"
            "app.listen(3000)\n"
        )
        patched, status = adapter.install_database_health_route(
            source, app_var="app", driver="mongoose"
        )
        self.assertEqual(status, "injected")
        # Exactly one gated handler (the injected one) plus the repository's
        # naive handler — and the gated one is registered first, otherwise
        # express would answer with the naive one.
        self.assertEqual(patched.count("app.get('/api/health'"), 2)
        first = patched.index("app.get('/api/health'")
        second = patched.index("app.get('/api/health'", first + 1)
        self.assertLess(first, second)
        self.assertLess(patched.index("readyState === 1"), second)

    def test_without_an_express_app_var_nothing_is_touched(self):
        source = "process.on('SIGTERM', () => {})\n"
        patched, status = adapter.install_database_health_route(
            source, app_var="", driver="mongoose"
        )
        self.assertEqual(status, "skipped")
        self.assertEqual(patched, source)

    def test_mongodb_driver_variant_uses_the_configured_variable(self):
        source = "const app = express()\napp.listen(5000)\n"
        patched, status = adapter.install_database_health_route(
            source, app_var="app", driver="mongodb", env_var="MONGODB_URI"
        )
        self.assertEqual(status, "injected")
        self.assertIn("MongoClient", patched)
        self.assertIn("MONGODB_URI", patched)

    def test_driver_detection_reads_the_application_source(self):
        self.assertEqual(
            adapter.detect_database_driver(["const m = require('mongoose')"]),
            "mongoose",
        )
        self.assertEqual(
            adapter.detect_database_driver(["const { MongoClient } = require('mongodb')"]),
            "mongodb",
        )
        self.assertEqual(adapter.detect_database_driver(["console.log(1)"]), "")

    def test_express_app_variable_is_detected(self):
        self.assertEqual(
            adapter.detect_express_app_var("const app = express()\n"), "app"
        )
        self.assertEqual(
            adapter.detect_express_app_var("const api = express()\n"), "api"
        )
        self.assertEqual(adapter.detect_express_app_var("const x = 1\n"), "")


class NginxStabilityTests(SimpleTestCase):
    LITERAL = """server {
    listen 80;
    location /api/ {
        proxy_pass http://backend:5000;
    }
    location / {
        proxy_pass http://frontend:80;
    }
}
"""

    def test_literal_upstreams_become_docker_dns_resolved(self):
        conf, report = adapter.stabilize_nginx_conf(self.LITERAL)
        self.assertTrue(report["changed"])
        self.assertEqual(report["upstreams"], 2)
        self.assertIn("resolver 127.0.0.11", conf)
        self.assertIn("set $cloudwise_upstream http://backend:5000;", conf)
        self.assertIn("proxy_pass $cloudwise_upstream;", conf)
        self.assertNotIn("proxy_pass http://backend:5000;", conf)

    def test_service_names_are_kept_and_no_container_ip_is_written(self):
        conf, _ = adapter.stabilize_nginx_conf(self.LITERAL)
        self.assertIn("backend:5000", conf)
        self.assertIn("frontend:80", conf)
        self.assertNotIn("172.", conf)
        self.assertNotIn("0.0.0.0", conf)

    def test_second_pass_is_a_no_op(self):
        once, _ = adapter.stabilize_nginx_conf(self.LITERAL)
        twice, report = adapter.stabilize_nginx_conf(once)
        self.assertEqual(once, twice)
        self.assertFalse(report["changed"])

    def test_ip_upstreams_are_left_untouched(self):
        conf = "server {\n    location / {\n        proxy_pass http://10.0.0.5:80;\n    }\n}\n"
        new_conf, report = adapter.stabilize_nginx_conf(conf)
        self.assertEqual(new_conf, conf)
        self.assertFalse(report["changed"])

    def test_existing_resolver_is_not_duplicated(self):
        conf = (
            "server {\n    resolver 127.0.0.11 valid=5s;\n"
            "    location /api/ {\n        proxy_pass http://backend:5000;\n    }\n}\n"
        )
        new_conf, report = adapter.stabilize_nginx_conf(conf)
        self.assertEqual(new_conf.count("resolver "), 1)
        self.assertTrue(report["changed"])

    def test_config_without_proxy_pass_is_untouched(self):
        conf = "server {\n    listen 80;\n}\n"
        new_conf, report = adapter.stabilize_nginx_conf(conf)
        self.assertEqual(new_conf, conf)
        self.assertEqual(report["reason"], "no_proxy_pass")


class ComposeEnvironmentTests(SimpleTestCase):
    COMPOSE = """services:
  backend:
    build:
      context: ./backend
    restart: unless-stopped
    environment:
      - PORT=5000
  nginx:
    image: nginx:alpine
"""

    def test_missing_database_variable_is_injected(self):
        new_text, report = adapter.ensure_backend_env_vars(
            self.COMPOSE, ["MONGO_URI"]
        )
        self.assertEqual(report["injected"], ["MONGO_URI"])
        self.assertIn("      - MONGO_URI=${MONGO_URI}", new_text)
        # Only the backend service changes.
        self.assertIn("  nginx:\n    image: nginx:alpine", new_text)

    def test_present_variable_is_not_duplicated(self):
        compose = self.COMPOSE.replace(
            "      - PORT=5000\n",
            "      - PORT=5000\n      - MONGO_URI=${MONGO_URI}\n",
        )
        new_text, report = adapter.ensure_backend_env_vars(
            compose, ["MONGO_URI"]
        )
        self.assertEqual(report["injected"], [])
        self.assertEqual(report["present"], ["MONGO_URI"])
        self.assertEqual(new_text, compose)
        # Exactly one entry — the call must not append a second one.
        self.assertEqual(new_text.count("      - MONGO_URI="), 1)

    def test_file_without_a_backend_service_is_untouched(self):
        compose = "services:\n  web:\n    image: nginx\n"
        new_text, report = adapter.ensure_backend_env_vars(
            compose, ["MONGO_URI"]
        )
        self.assertEqual(new_text, compose)
        self.assertEqual(report["skipped"], ["MONGO_URI"])
        self.assertEqual(report["reason"], "no_backend_service")

    def test_mapping_style_environment_is_reported_not_guessed(self):
        compose = (
            "services:\n  backend:\n    environment:\n"
            "      PORT: 5000\n"
        )
        new_text, report = adapter.ensure_backend_env_vars(
            compose, ["MONGO_URI"]
        )
        self.assertEqual(new_text, compose)
        self.assertEqual(report["skipped"], ["MONGO_URI"])
        self.assertEqual(report["reason"], "mapping_environment")

    def test_environment_key_is_created_when_absent(self):
        compose = "services:\n  backend:\n    image: node\n  nginx:\n    image: nginx\n"
        new_text, report = adapter.ensure_backend_env_vars(
            compose, ["MONGO_URI"]
        )
        self.assertEqual(report["injected"], ["MONGO_URI"])
        self.assertIn("    environment:\n      - MONGO_URI=${MONGO_URI}", new_text)


class FailureClassificationTests(SimpleTestCase):
    """A–H: every failure mode gets its own code, never a bare message."""

    ATLAS = {"configured": True, "atlas": True, "host": "c0.abc.mongodb.net"}
    PREFLIGHT_OK = {
        "status": STATUS_SUCCESS,
        "kind": "mongodb",
        "host": "cluster0.abc.mongodb.net",
        "proxy": {"origin": "nginx"},
    }

    def test_a_instance_not_running(self):
        code, _ = classify_health_failure(
            health_message="Health check failed",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 0},
                          "frontend": {"ok": False}},
            diagnostics="EC2 instance i-123 did not reach running state",
        )
        self.assertEqual(code, ERROR_EC2_UNAVAILABLE)

    def test_b_docker_unavailable(self):
        code, _ = classify_health_failure(
            health_message="Health check failed",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 0},
                          "frontend": {"ok": False}},
            diagnostics="Cannot connect to the Docker daemon",
        )
        self.assertEqual(code, ERROR_DOCKER_UNAVAILABLE)

    def test_c_container_exited(self):
        code, message = classify_health_failure(
            health_message="Health check failed",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 502},
                          "frontend": {"ok": True, "statusCode": 200}},
            diagnostics=(
                "NAME                STATUS\n"
                "proj-backend-1       Exited (1) 40 seconds ago\n"
            ),
        )
        self.assertEqual(code, ERROR_CONTAINER_FAILED)
        self.assertIn("backend", message)

    def test_d_backend_not_running_keeps_its_code(self):
        code, _ = classify_health_failure(
            health_message="HTTP 502 from 127.0.0.1:80",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 502, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight=self.PREFLIGHT_OK,
            app_port=80,
        )
        self.assertEqual(code, ERROR_BACKEND_NOT_RUNNING)

    def test_e_mongodb_authentication_failure(self):
        code, message = classify_health_failure(
            health_message="Split health check failed: backend HTTP 503",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 503, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight=self.PREFLIGHT_OK,
            diagnostics="MongooseServerSelectionError: Authentication failed",
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
        )
        self.assertEqual(code, ERROR_DATABASE_AUTH_FAILED)
        self.assertIn("authentication", message.lower())
        _assert_no_secret(self, message)

    def test_f_atlas_network_blocked_reports_the_required_text(self):
        code, message = classify_health_failure(
            health_message="Split health check failed: backend HTTP 503",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 503, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight=self.PREFLIGHT_OK,
            diagnostics=(
                "MongooseServerSelectionError: Could not connect to any "
                "servers in your MongoDB Atlas cluster (ReplicaSetNoPrimary)"
            ),
            atlas=self.ATLAS,
            public_ip="203.0.113.10",
        )
        self.assertEqual(code, ERROR_MONGODB_ATLAS_NETWORK_BLOCKED)
        self.assertIn(
            "MongoDB Atlas network access blocked the EC2 instance.", message
        )
        self.assertIn(
            "CloudWise could not establish the backend database connection.",
            message,
        )
        self.assertIn(
            "Configure MongoDB Atlas Network Access or configure Atlas API "
            "credentials for automatic allowlisting.",
            message,
        )
        self.assertIn("203.0.113.10/32", message)
        _assert_no_secret(self, message)

    def test_f_without_atlas_credentials_explains_what_is_missing(self):
        code, message = classify_health_failure(
            health_message="Split health check failed: backend HTTP 503",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 503, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight=self.PREFLIGHT_OK,
            diagnostics="ReplicaSetNoPrimary",
            atlas={"configured": False, "atlas": True},
            public_ip="203.0.113.10",
        )
        self.assertEqual(code, ERROR_MONGODB_ATLAS_NOT_CONFIGURED)
        self.assertIn(
            "MongoDB Atlas Network Access must allow the EC2 public IP",
            message,
        )
        self.assertIn("MONGODB_ATLAS_PUBLIC_KEY", message)

    def test_f_without_atlas_credentials_message_is_actionable(self):
        message = atlas_blocked_message("203.0.113.10", configured=False)
        self.assertIn("203.0.113.10/32", message)
        self.assertIn("never 0.0.0.0/0", message)
        self.assertIn("must allow the EC2 public IP", message)

    def test_g_nginx_and_frontend_failures_keep_their_codes(self):
        code, _ = classify_health_failure(
            health_message="HTTP 000 from 127.0.0.1:80",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 0},
                          "frontend": {"ok": False}},
            preflight=self.PREFLIGHT_OK,
        )
        self.assertEqual(code, ERROR_NGINX_PROXY_FAILED)

        code, _ = classify_health_failure(
            health_message="HTTP 404 from 127.0.0.1:80",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 200, "ok": True},
                          "frontend": {"ok": False, "statusCode": 404}},
            preflight=self.PREFLIGHT_OK,
        )
        self.assertEqual(code, ERROR_FRONTEND_FAILED)

    def test_h_health_endpoint_answered_but_is_not_healthy(self):
        code, message = classify_health_failure(
            health_message="Split health check failed: backend HTTP 404",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 404, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight={"status": STATUS_SUCCESS, "kind": "none"},
            diagnostics="",
        )
        self.assertEqual(code, ERROR_HEALTH_ENDPOINT_FAILED)
        self.assertIn("404", message)

    def test_diagnostics_are_optional(self):
        code, _ = classify_health_failure(
            health_message="HTTP 502 from 127.0.0.1:80",
            split_report={"status": "FAILED",
                          "backend": {"statusCode": 502, "ok": False},
                          "frontend": {"ok": True, "statusCode": 200}},
            preflight=self.PREFLIGHT_OK,
        )
        self.assertEqual(code, ERROR_BACKEND_NOT_RUNNING)


class AtlasProviderStepTests(SimpleTestCase):
    def _provider(self, **config):
        return AwsEc2Provider(config=config)

    def test_no_atlas_uri_means_nothing_is_attempted(self):
        log = MagicMock()
        report = self._provider(
            env_vars={"MONGO_URI": "mongodb://db.local/app"},
            files={"backend/server.js": "const m = require('mongoose')"},
        )._ensure_atlas_network_access(
            env_vars={"MONGO_URI": "mongodb://db.local/app"},
            deployment_id="dep-1",
            public_ip="203.0.113.10",
            log=log,
        )
        self.assertFalse(report["atlas"])
        self.assertEqual(report["action"], "skipped")

    @override_settings(MONGODB_ATLAS_AUTO_ALLOWLIST=False)
    def test_disabled_automation_reports_how_to_allow_manually(self):
        report = self._provider()._ensure_atlas_network_access(
            env_vars={"MONGO_URI": ATLAS_URI},
            deployment_id="dep-1",
            public_ip="203.0.113.10",
            log=MagicMock(),
        )
        self.assertEqual(report["action"], "disabled")
        self.assertFalse(report["configured"])
        self.assertIn("203.0.113.10/32", report["message"])

    @override_settings(
        MONGODB_ATLAS_PUBLIC_KEY="",
        MONGODB_ATLAS_PRIVATE_KEY="",
        MONGODB_ATLAS_PROJECT_ID="",
    )
    def test_missing_credentials_never_pretend_success(self):
        log = MagicMock()
        report = self._provider()._ensure_atlas_network_access(
            env_vars={"MONGO_URI": ATLAS_URI},
            deployment_id="dep-1",
            public_ip="203.0.113.10",
            log=log,
        )
        self.assertFalse(report["configured"])
        self.assertNotEqual(report["action"], "added")
        warnings = [entry for entry in log.warning.call_args_list]
        self.assertTrue(warnings)
        joined = " ".join(str(call) for call in warnings)
        self.assertIn("not configured", joined)
        _assert_no_secret(self, report)

    @override_settings(
        MONGODB_ATLAS_PUBLIC_KEY="pk",
        MONGODB_ATLAS_PRIVATE_KEY="sk",
        MONGODB_ATLAS_PROJECT_ID="64f000000000000000000001",
    )
    def test_successful_allowlist_is_logged_without_secrets(self):
        log = MagicMock()
        with patch.object(
            atlas_module := __import__(
                "api.services.deployment.mongodb_atlas_service",
                fromlist=["ensure_atlas_access_entry"],
            ),
            "ensure_atlas_access_entry",
            return_value={
                "configured": True,
                "action": "added",
                "cidr": "203.0.113.10/32",
                "message": "Added MongoDB Atlas Network Access entry.",
            },
        ):
            report = self._provider()._ensure_atlas_network_access(
                env_vars={"MONGO_URI": ATLAS_URI},
                deployment_id="dep-1",
                public_ip="203.0.113.10",
                log=log,
            )
        self.assertEqual(report["action"], "added")
        self.assertTrue(report["configured"])
        _assert_no_secret(self, report)
        _assert_no_secret(self, log.info.call_args_list)

    def test_api_error_does_not_raise(self):
        """A blocked Admin API must never abort the deployment."""
        with patch.object(
            atlas,
            "ensure_atlas_access_entry",
            side_effect=RuntimeError("boom"),
        ):
            report = self._provider()._ensure_atlas_network_access(
                env_vars={"MONGO_URI": ATLAS_URI},
                deployment_id="dep-1",
                public_ip="203.0.113.10",
                log=MagicMock(),
            )
        self.assertEqual(report["action"], "failed")

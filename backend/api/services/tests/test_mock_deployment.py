"""
Isolated tests for the mock deployment architecture.

Tests cover:
  - All DeploymentStatus values are defined
  - All DeploymentStage values are defined
  - Valid status transitions
  - Invalid status transitions
  - make_log_entry schema and validation
  - DeploymentLogService write / query
  - MockDeploymentProvider: successful deployment lifecycle
  - MockDeploymentProvider: unsupported provider rejection
  - MockDeploymentProvider: health check (simulated, not real)
  - MockDeploymentProvider: rollback (simulated, not real)
  - MockDeploymentProvider: structured log entries after lifecycle
  - No AWS calls, no secrets in any log
  - DeploymentHealthCheckService normalisation
  - DeploymentRollbackService normalisation

These tests do NOT touch any existing test file or database.
"""

from django.test import SimpleTestCase

from api.services.deployment.status import (
    DeploymentStatus,
    DeploymentStage,
    is_valid_transition,
    get_allowed_transitions,
)
from api.services.deployment.log_service import (
    DeploymentLogService,
    make_log_entry,
)
from api.services.deployment.mock_provider import (
    MockDeploymentProvider,
    UnsupportedProviderError,
    clear_mock_store,
)
from api.services.deployment.health_check import DeploymentHealthCheckService
from api.services.deployment.rollback import DeploymentRollbackService


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

SECRET_KEYWORDS = (
    "aws_access_key",
    "aws_secret",
    "github_token",
    "password",
    "private_key",
    "secret_key",
    "credential",
)


def _has_secret(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in SECRET_KEYWORDS)


def _assert_no_secrets(test_case: SimpleTestCase, entries: list[dict]) -> None:
    for entry in entries:
        msg = entry.get("message", "")
        test_case.assertFalse(
            _has_secret(msg),
            f"Log entry contains a secret keyword: {msg!r}",
        )


# ---------------------------------------------------------------------------
# Status tests
# ---------------------------------------------------------------------------

class TestDeploymentStatus(SimpleTestCase):

    def test_all_statuses_defined(self):
        expected = {
            "QUEUED", "PREPARING", "BUILDING", "DEPLOYING",
            "HEALTH_CHECK", "RUNNING", "FAILED", "ROLLING_BACK", "ROLLED_BACK",
        }
        self.assertEqual(set(DeploymentStatus.ALL), expected)

    def test_status_constants_match_all_tuple(self):
        for status in DeploymentStatus.ALL:
            self.assertIsInstance(status, str)
            self.assertTrue(len(status) > 0)

    def test_all_stages_defined(self):
        expected = {
            "PREPARING", "BUILDING", "DEPLOYING",
            "HEALTH_CHECK", "COMPLETED", "FAILED", "ROLLBACK",
        }
        self.assertEqual(set(DeploymentStage.ALL), expected)


# ---------------------------------------------------------------------------
# Transition tests
# ---------------------------------------------------------------------------

class TestStatusTransitions(SimpleTestCase):

    def test_queued_to_preparing_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.QUEUED, DeploymentStatus.PREPARING))

    def test_queued_to_failed_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.QUEUED, DeploymentStatus.FAILED))

    def test_preparing_to_building_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.PREPARING, DeploymentStatus.BUILDING))

    def test_building_to_deploying_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.BUILDING, DeploymentStatus.DEPLOYING))

    def test_deploying_to_health_check_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.DEPLOYING, DeploymentStatus.HEALTH_CHECK))

    def test_health_check_to_running_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.HEALTH_CHECK, DeploymentStatus.RUNNING))

    def test_running_to_rolling_back_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.RUNNING, DeploymentStatus.ROLLING_BACK))

    def test_rolling_back_to_rolled_back_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.ROLLING_BACK, DeploymentStatus.ROLLED_BACK))

    def test_failed_to_rolling_back_is_valid(self):
        self.assertTrue(is_valid_transition(DeploymentStatus.FAILED, DeploymentStatus.ROLLING_BACK))

    def test_rolled_back_has_no_transitions(self):
        allowed = get_allowed_transitions(DeploymentStatus.ROLLED_BACK)
        self.assertEqual(len(allowed), 0)

    def test_queued_to_running_is_invalid(self):
        self.assertFalse(is_valid_transition(DeploymentStatus.QUEUED, DeploymentStatus.RUNNING))

    def test_running_to_queued_is_invalid(self):
        self.assertFalse(is_valid_transition(DeploymentStatus.RUNNING, DeploymentStatus.QUEUED))

    def test_rolled_back_to_running_is_invalid(self):
        self.assertFalse(is_valid_transition(DeploymentStatus.ROLLED_BACK, DeploymentStatus.RUNNING))

    def test_unknown_status_returns_false(self):
        self.assertFalse(is_valid_transition("NOT_A_STATUS", DeploymentStatus.RUNNING))


# ---------------------------------------------------------------------------
# Log service tests
# ---------------------------------------------------------------------------

class TestMakeLogEntry(SimpleTestCase):

    def test_returns_required_keys(self):
        entry = make_log_entry(DeploymentStage.BUILDING, "Docker build started")
        self.assertIn("timestamp", entry)
        self.assertIn("level", entry)
        self.assertIn("stage", entry)
        self.assertIn("message", entry)

    def test_default_level_is_info(self):
        entry = make_log_entry(DeploymentStage.PREPARING, "Starting")
        self.assertEqual(entry["level"], "INFO")

    def test_warning_level(self):
        entry = make_log_entry(DeploymentStage.BUILDING, "Low disk space", level="WARNING")
        self.assertEqual(entry["level"], "WARNING")

    def test_error_level(self):
        entry = make_log_entry(DeploymentStage.FAILED, "Build error", level="ERROR")
        self.assertEqual(entry["level"], "ERROR")

    def test_custom_timestamp_is_preserved(self):
        ts = "2026-01-01T00:00:00Z"
        entry = make_log_entry(DeploymentStage.DEPLOYING, "Deploy step", timestamp=ts)
        self.assertEqual(entry["timestamp"], ts)

    def test_invalid_stage_raises_value_error(self):
        with self.assertRaises(ValueError):
            make_log_entry("UNKNOWN_STAGE", "msg")

    def test_invalid_level_raises_value_error(self):
        with self.assertRaises(ValueError):
            make_log_entry(DeploymentStage.BUILDING, "msg", level="DEBUG")  # type: ignore[arg-type]

    def test_no_secrets_in_log_entry(self):
        entry = make_log_entry(DeploymentStage.BUILDING, "Docker image built")
        self.assertFalse(_has_secret(entry["message"]))


class TestDeploymentLogService(SimpleTestCase):

    def setUp(self):
        self.svc = DeploymentLogService("dep_test_123")

    def test_initial_log_is_empty(self):
        self.assertEqual(self.svc.count(), 0)

    def test_info_adds_entry(self):
        self.svc.info(DeploymentStage.BUILDING, "Build started")
        self.assertEqual(self.svc.count(), 1)
        self.assertEqual(self.svc.all()[0]["level"], "INFO")

    def test_warning_adds_entry(self):
        self.svc.warning(DeploymentStage.DEPLOYING, "Slow network")
        self.assertEqual(self.svc.all()[0]["level"], "WARNING")

    def test_error_adds_entry(self):
        self.svc.error(DeploymentStage.FAILED, "Build crashed")
        self.assertEqual(self.svc.all()[0]["level"], "ERROR")

    def test_by_stage_filters_correctly(self):
        self.svc.info(DeploymentStage.BUILDING, "Build started")
        self.svc.info(DeploymentStage.DEPLOYING, "Deploy started")
        building = self.svc.by_stage(DeploymentStage.BUILDING)
        self.assertEqual(len(building), 1)
        self.assertEqual(building[0]["stage"], DeploymentStage.BUILDING)

    def test_all_returns_copy(self):
        self.svc.info(DeploymentStage.PREPARING, "Prepare")
        copy = self.svc.all()
        copy.clear()
        self.assertEqual(self.svc.count(), 1)  # original unaffected

    def test_clear_empties_log(self):
        self.svc.info(DeploymentStage.BUILDING, "Entry")
        self.svc.clear()
        self.assertEqual(self.svc.count(), 0)


# ---------------------------------------------------------------------------
# MockDeploymentProvider tests
# ---------------------------------------------------------------------------

class TestMockDeploymentProviderSuccess(SimpleTestCase):

    def setUp(self):
        clear_mock_store()
        self.provider = MockDeploymentProvider()

    def test_provider_type_is_mock(self):
        self.assertEqual(self.provider.PROVIDER_TYPE, "MOCK")

    def test_start_returns_deployment_id(self):
        result = self.provider.start({"environment_name": "test-env", "provider": "MOCK"})
        self.assertIn("deployment_id", result)
        self.assertTrue(result["deployment_id"].startswith("mock_"))

    def test_start_returns_queued_status(self):
        result = self.provider.start({"environment_name": "test-env"})
        self.assertEqual(result["status"], DeploymentStatus.QUEUED)

    def test_start_marks_result_as_simulated(self):
        result = self.provider.start({"environment_name": "test-env"})
        self.assertTrue(result["simulated"])

    def test_start_requires_environment_name(self):
        with self.assertRaises(ValueError):
            self.provider.start({})

    def test_get_status_advances_lifecycle(self):
        start = self.provider.start({"environment_name": "lifecycle-env"})
        dep_id = start["deployment_id"]
        # Each call should advance the state
        status1 = self.provider.get_status(dep_id)
        self.assertNotEqual(status1["status"], DeploymentStatus.QUEUED)

    def test_get_status_progress_increases(self):
        start = self.provider.start({"environment_name": "progress-env"})
        dep_id = start["deployment_id"]
        status = self.provider.get_status(dep_id)
        self.assertGreater(status["progress"], 0)

    def test_get_status_result_is_simulated(self):
        start = self.provider.start({"environment_name": "sim-env"})
        status = self.provider.get_status(start["deployment_id"])
        self.assertTrue(status["simulated"])

    def test_get_logs_returns_list(self):
        start = self.provider.start({"environment_name": "log-env"})
        logs = self.provider.get_logs(start["deployment_id"])
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0)

    def test_get_logs_entries_have_required_keys(self):
        start = self.provider.start({"environment_name": "log-env"})
        logs = self.provider.get_logs(start["deployment_id"])
        for entry in logs:
            self.assertIn("timestamp", entry)
            self.assertIn("level", entry)
            self.assertIn("stage", entry)
            self.assertIn("message", entry)

    def test_no_secrets_in_start_logs(self):
        result = self.provider.start({
            "environment_name": "secret-test",
            "token": "ghp_SECRETTOKEN",
            "password": "hunter2",
        })
        logs = self.provider.get_logs(result["deployment_id"])
        _assert_no_secrets(self, logs)

    def test_secrets_stripped_from_configuration(self):
        result = self.provider.start({
            "environment_name": "strip-test",
            "aws_access_key_id": "AKIAIOSFODNN7EXAMPLE",
            "github_token": "ghp_xxxx",
            "password": "s3cr3t",
        })
        cfg = result.get("configuration", {})
        self.assertNotIn("aws_access_key_id", cfg)
        self.assertNotIn("github_token", cfg)
        self.assertNotIn("password", cfg)
        self.assertIn("environment_name", cfg)

    def test_full_lifecycle_reaches_running(self):
        """Advance through all lifecycle steps until RUNNING."""
        start = self.provider.start({"environment_name": "full-lifecycle"})
        dep_id = start["deployment_id"]

        for _ in range(10):  # More iterations than lifecycle steps
            status = self.provider.get_status(dep_id)
            if status["status"] == DeploymentStatus.RUNNING:
                break

        self.assertEqual(status["status"], DeploymentStatus.RUNNING)
        self.assertEqual(status["progress"], 100)


class TestMockDeploymentProviderFailure(SimpleTestCase):

    def setUp(self):
        clear_mock_store()
        self.provider = MockDeploymentProvider()

    def test_unsupported_provider_raises_error(self):
        with self.assertRaises(UnsupportedProviderError):
            self.provider.start({"environment_name": "invalid-attempt", "provider": "INVALID_PROVIDER"})

    def test_unsupported_provider_unknown_cloud_raises_error(self):
        with self.assertRaises(UnsupportedProviderError):
            self.provider.start({"environment_name": "unknown-attempt", "provider": "UNKNOWN_CLOUD"})

    def test_unknown_deployment_id_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.provider.get_status("mock_doesnotexist000")

    def test_get_logs_unknown_id_raises_key_error(self):
        with self.assertRaises(KeyError):
            self.provider.get_logs("mock_doesnotexist000")


class TestMockHealthCheck(SimpleTestCase):

    def setUp(self):
        clear_mock_store()
        self.provider = MockDeploymentProvider()
        self.svc = DeploymentHealthCheckService(self.provider)

    def test_health_check_returns_healthy(self):
        start = self.provider.start({"environment_name": "hc-env"})
        result = self.svc.run(start["deployment_id"])
        self.assertTrue(result["healthy"])

    def test_health_check_result_is_simulated(self):
        start = self.provider.start({"environment_name": "hc-sim-env"})
        result = self.provider.health_check(start["deployment_id"])
        self.assertTrue(result["simulated"])

    def test_health_check_does_not_claim_real_server(self):
        start = self.provider.start({"environment_name": "hc-real-env"})
        result = self.provider.health_check(start["deployment_id"])
        detail = result.get("detail", {})
        # http_status and latency_ms must be None — no real HTTP request
        self.assertIsNone(detail.get("http_status"))
        self.assertIsNone(detail.get("latency_ms"))

    def test_health_check_provider_type_is_mock(self):
        start = self.provider.start({"environment_name": "hc-type-env"})
        result = self.svc.run(start["deployment_id"])
        self.assertEqual(result["provider_type"], "MOCK")

    def test_health_check_logs_added(self):
        start = self.provider.start({"environment_name": "hc-log-env"})
        dep_id = start["deployment_id"]
        self.provider.health_check(dep_id)
        logs = self.provider.get_logs(dep_id)
        hc_logs = [e for e in logs if e["stage"] == DeploymentStage.HEALTH_CHECK]
        self.assertGreater(len(hc_logs), 0)

    def test_no_secrets_in_health_check_logs(self):
        start = self.provider.start({"environment_name": "hc-secret-env"})
        dep_id = start["deployment_id"]
        self.provider.health_check(dep_id)
        logs = self.provider.get_logs(dep_id)
        _assert_no_secrets(self, logs)


class TestMockRollback(SimpleTestCase):

    def setUp(self):
        clear_mock_store()
        self.provider = MockDeploymentProvider()
        self.svc = DeploymentRollbackService(self.provider)

    def test_rollback_returns_rolled_back_status(self):
        start = self.provider.start({"environment_name": "rb-env"})
        result = self.svc.run(start["deployment_id"])
        self.assertEqual(result["status"], DeploymentStatus.ROLLED_BACK)

    def test_rollback_result_is_simulated(self):
        start = self.provider.start({"environment_name": "rb-sim-env"})
        result = self.provider.rollback(start["deployment_id"])
        self.assertTrue(result["simulated"])

    def test_rollback_provider_type_is_mock(self):
        start = self.provider.start({"environment_name": "rb-type-env"})
        result = self.svc.run(start["deployment_id"])
        self.assertEqual(result["provider_type"], "MOCK")

    def test_rollback_returns_logs(self):
        start = self.provider.start({"environment_name": "rb-log-env"})
        result = self.provider.rollback(start["deployment_id"])
        self.assertIsInstance(result["logs"], list)
        self.assertGreater(len(result["logs"]), 0)

    def test_rollback_logs_have_rollback_stage(self):
        start = self.provider.start({"environment_name": "rb-stage-env"})
        result = self.provider.rollback(start["deployment_id"])
        stages = {e["stage"] for e in result["logs"]}
        self.assertIn(DeploymentStage.ROLLBACK, stages)

    def test_no_secrets_in_rollback_logs(self):
        start = self.provider.start({"environment_name": "rb-secret-env"})
        dep_id = start["deployment_id"]
        result = self.provider.rollback(dep_id)
        _assert_no_secrets(self, result["logs"])

    def test_rollback_resets_progress_to_zero(self):
        start = self.provider.start({"environment_name": "rb-progress-env"})
        dep_id = start["deployment_id"]
        self.provider.rollback(dep_id)
        status = self.provider.get_status(dep_id)
        self.assertEqual(status["progress"], 0)

from django.test import SimpleTestCase

from api.services.deployment.adapters import (
    generate_split_deployment,
    readiness_problem,
    verify_split_deployment,
)
from api.services.deployment.adapters.live_verification import (
    FAILED_STATUS,
    HEALTHY_STATUS,
    SKIPPED_STATUS,
    build_probe_command,
)
from api.services.deployment.repository_detector import detect_repository
from api.services.deployment_file_generator import generate_deployment_files
from api.services.tests.test_repository_detector import TARGET_REPO_FILES

SPLIT_FILE_ORDER = [
    "frontend/Dockerfile",
    "backend/Dockerfile",
    "docker-compose.yml",
    "nginx.conf",
]


class SplitGenerationTests(SimpleTestCase):
    """End-to-end generation for the separate frontend/ + backend/ repo."""

    def setUp(self):
        self.result = generate_deployment_files(TARGET_REPO_FILES, provider="AWS")
        self.files = self.result["files"]
        self.plan = self.result["deploymentPlan"]

    def test_generated_file_set_and_order(self):
        self.assertEqual(list(self.files.keys())[:4], SPLIT_FILE_ORDER)
        self.assertNotIn("Dockerfile", self.files)
        self.assertNotIn("vercel.json", self.files)
        self.assertNotIn("render.yaml", self.files)
        self.assertIn(".github/workflows/deploy.yml", self.files)
        self.assertFalse(self.result["dockerfile_preserved"])
        self.assertFalse(self.result["compose_preserved"])
        self.assertEqual(self.result["port"], 80)

    def test_backend_dockerfile_uses_detected_port_and_exec_form_cmd(self):
        dockerfile = self.files["backend/Dockerfile"]

        self.assertIn("EXPOSE 5000", dockerfile)
        self.assertIn("ENV NODE_ENV=production PORT=5000", dockerfile)
        self.assertIn('CMD ["npm", "start"]', dockerfile)
        self.assertNotIn('CMD ["npm start"]', dockerfile)
        self.assertIn("npm ci --omit=dev", dockerfile)

    def test_frontend_dockerfile_builds_static_spa_with_fallback(self):
        dockerfile = self.files["frontend/Dockerfile"]

        self.assertIn("AS builder", dockerfile)
        self.assertIn("RUN npm ci", dockerfile)
        self.assertIn("RUN npm run build", dockerfile)
        self.assertIn("COPY --from=builder /app/dist", dockerfile)
        self.assertIn("try_files $uri $uri/ /index.html", dockerfile)
        self.assertIn("EXPOSE 80", dockerfile)
        self.assertIn('CMD ["nginx", "-g", "daemon off;"]', dockerfile)

    def test_frontend_nginx_denies_secret_paths_but_keeps_client_routes(self):
        dockerfile = self.files["frontend/Dockerfile"]

        # printf collapses "\\" to "\", so the conf nginx reads holds the
        # same "\.env" rule the router conf has.
        self.assertIn(r'location ~* "\\.env($|\\.)" { return 404; }', dockerfile)
        self.assertIn(r'location ~* "\\.git(/|$)" { return 404; }', dockerfile)
        self.assertIn("try_files $uri $uri/ /index.html;", dockerfile)
        self.assertIn("location / {", dockerfile)

    def test_plan_reports_that_secret_paths_are_denied(self):
        self.assertTrue(self.plan["nginxSensitivePathsDenied"])

    def test_a_preserved_router_conf_is_reported_without_the_deny_rules(self):
        result = generate_deployment_files(
            {
                "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
                "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
                "nginx.conf": (
                    "server {\n    listen 80;\n"
                    "    location / { try_files $uri /index.html; }\n}\n"
                ),
            },
            provider="AWS",
        )

        self.assertNotIn(
            "cloudwise-deny-sensitive-paths", result["files"]["nginx.conf"]
        )
        self.assertFalse(
            result["deploymentPlan"]["nginxSensitivePathsDenied"]
        )

    def test_nginx_routes_api_to_detected_backend_port(self):
        nginx = self.files["nginx.conf"]

        self.assertIn("location /api/", nginx)
        # The upstream stays the Compose service name and is resolved per
        # request (never a container IP that goes stale).
        self.assertIn("http://backend:5000", nginx)
        self.assertIn("http://frontend:80", nginx)
        self.assertIn("proxy_pass $cloudwise_upstream;", nginx)
        self.assertIn("resolver 127.0.0.11", nginx)
        self.assertIn("location /", nginx)

    def test_compose_keeps_backend_internal_and_passes_env(self):
        compose = self.files["docker-compose.yml"]

        self.assertIn('"80:80"', compose)
        self.assertNotIn('"5000:5000"', compose)
        self.assertIn("context: ./frontend", compose)
        self.assertIn("context: ./backend", compose)
        self.assertIn("- PORT=5000", compose)
        self.assertIn("- MONGO_URI=${MONGO_URI}", compose)
        self.assertIn("nginx:", compose)
        lowered = compose.lower()
        self.assertNotIn("image: mongo", lowered)
        self.assertNotIn("image: postgres", lowered)
        self.assertNotIn("image: mysql", lowered)

    def test_compose_yaml_indentation_is_valid(self):
        compose = self.files["docker-compose.yml"]

        for line in compose.splitlines():
            stripped = line.lstrip(" ")
            if stripped.startswith(("context:", "args:", "- ", "environment:",
                                    "ports:", "volumes:", "depends_on:",
                                    "image:", "build:")):
                continue
            if stripped.startswith("restart:"):
                # restart is a service-level key: exactly 4 spaces.
                self.assertEqual(len(line) - len(stripped), 4, line)
        # No restart key may sit inside a build: mapping (compose rejects
        # additional properties there).
        lines = compose.splitlines()
        in_build = False
        build_indent = 0
        for line in lines:
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            if stripped.startswith("build:"):
                in_build = True
                build_indent = indent
            elif in_build and stripped and indent <= build_indent:
                in_build = False
            elif in_build and stripped.startswith("restart:"):
                self.fail("restart must not be nested under build:")

    def test_deployment_plan_carries_split_manifest(self):
        plan = self.plan

        self.assertEqual(plan["target"], "AWS_EC2")
        self.assertEqual(plan["containers"], ["frontend", "backend", "nginx"])
        self.assertEqual(plan["generatedFiles"][:4], SPLIT_FILE_ORDER)
        self.assertEqual(plan["ports"], [80])
        self.assertTrue(plan["requiresNginx"])
        self.assertEqual(plan["architecture"], "separate_frontend_backend")
        self.assertEqual(plan["backendPort"], 5000)
        self.assertEqual(plan["frontendPort"], 80)
        self.assertEqual(plan["portEvidence"], "source")
        self.assertEqual(plan["apiBasePaths"], ["/api/v1"])
        self.assertEqual(
            plan["apiProbePaths"][0], "/api/v1/doctors",
        )
        self.assertEqual(plan["issues"], [])
        self.assertEqual(plan["manifest"]["backend"]["startCommand"], "npm start")
        self.assertEqual(plan["database"], {"type": "MongoDB", "detected": True})
        self.assertIn("MONGO_URI", plan["requiredEnvVars"])

    def test_detection_summary_is_unchanged_format(self):
        detection = self.result["detection"]

        self.assertEqual(detection["frontend"], "React + Vite")
        self.assertEqual(detection["backend"], "Express")
        self.assertEqual(detection["database"], "MongoDB")
        self.assertEqual(detection["applicationType"], "full-stack")

    def test_readiness_problem_is_none_for_target_repo(self):
        self.assertIsNone(readiness_problem(self.plan))


class BuildTimeEnvTests(SimpleTestCase):
    FILES = {
        "frontend/package.json": (
            '{"dependencies":{"react":"18.3.1"},'
            '"devDependencies":{"vite":"5.4.0","@vitejs/plugin-react":"4.3.0"}}'
        ),
        "frontend/src/main.jsx": (
            "const base = import.meta.env.VITE_API_BASE_URL\n"
            "fetch('/api/v1/doctors')\n"
        ),
        "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
        "backend/server.js": "require('express')().listen(4000)\n",
    }

    def test_frontend_build_args_are_declared_and_passed_by_compose(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        dockerfile = result["files"]["frontend/Dockerfile"]
        compose = result["files"]["docker-compose.yml"]

        self.assertIn("ARG VITE_API_BASE_URL", dockerfile)
        self.assertIn("ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}", dockerfile)
        self.assertIn("args:", compose)
        self.assertIn("- VITE_API_BASE_URL=${VITE_API_BASE_URL:-}", compose)
        # restart stays a service-level key even when build.args is present.
        self.assertIn("\n    restart: unless-stopped", compose)
        # No hardcoded local endpoints anywhere in the generated files.
        self.assertNotIn("localhost", dockerfile)
        self.assertNotIn("127.0.0.1", dockerfile)
        self.assertNotIn("localhost", compose)

    def test_probe_paths_prefer_backend_endpoints(self):
        result = generate_deployment_files(self.FILES, provider="AWS")
        plan = result["deploymentPlan"]

        self.assertIn("/api/v1/doctors", plan["apiProbePaths"])


class ExistingFilePreservationTests(SimpleTestCase):
    def test_existing_service_dockerfiles_compose_and_nginx_are_kept(self):
        files = {
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "frontend/Dockerfile": "FROM custom-fe:1\nEXPOSE 8081\n",
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
            "backend/Dockerfile": "FROM custom-be:1\nEXPOSE 9099\n",
            "docker-compose.yml": "services:\n  app:\n    image: custom\n",
            "nginx.conf": "server { listen 8088; }\n",
        }
        result = generate_deployment_files(files, provider="AWS")

        self.assertEqual(result["files"]["frontend/Dockerfile"],
                         files["frontend/Dockerfile"])
        self.assertEqual(result["files"]["backend/Dockerfile"],
                         files["backend/Dockerfile"])
        self.assertEqual(result["files"]["docker-compose.yml"],
                         files["docker-compose.yml"])
        self.assertEqual(result["files"]["nginx.conf"], files["nginx.conf"])
        self.assertTrue(result["dockerfile_preserved"])
        self.assertTrue(result["compose_preserved"])


class ReadinessProblemTests(SimpleTestCase):
    def test_missing_start_command_is_actionable(self):
        result = generate_deployment_files({
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
        })
        problem = readiness_problem(result["deploymentPlan"])

        self.assertIsNotNone(problem)
        self.assertIn("start", problem)
        self.assertIn("backend/package.json", problem)

    def test_non_split_plan_is_never_gated(self):
        result = generate_deployment_files({
            "package.json": '{"dependencies":{"express":"4.19.2"}}',
        })

        self.assertNotIn("architecture", result["deploymentPlan"])
        self.assertIsNone(readiness_problem(result["deploymentPlan"]))

    def test_empty_plan_is_never_gated(self):
        self.assertIsNone(readiness_problem({}))
        self.assertIsNone(readiness_problem(None))


class DirectAdapterEntryTests(SimpleTestCase):
    def test_generate_split_deployment_matches_legacy_result_shape(self):
        files = dict(TARGET_REPO_FILES)
        profile = detect_repository(files)
        from api.services.tech_stack_detector import analyze_repository

        analysis = analyze_repository(files)
        result = generate_split_deployment(
            files, profile, analysis=analysis, provider="AWS",
        )

        for key in (
            "technology", "dockerfile_preserved", "compose_preserved",
            "cicd_preserved", "port", "files", "detection", "analysis",
            "deploymentPlan",
        ):
            self.assertIn(key, result)
        self.assertEqual(list(result["files"].keys())[:4], SPLIT_FILE_ORDER)

    def test_non_split_profile_is_refused_by_detector_gate(self):
        profile = detect_repository({"package.json": '{"dependencies":{}}'})

        self.assertFalse(profile.requires_separate_frontend_backend)


class LiveVerificationTests(SimpleTestCase):
    PLAN = {
        "architecture": "separate_frontend_backend",
        "apiProbePaths": ["/api/v1/doctors"],
        "apiBasePaths": ["/api/v1"],
    }

    @staticmethod
    def _runner(output: str, seen: dict | None = None):
        def run(commands, stage_message, timeout_seconds):
            if seen is not None:
                seen["commands"] = list(commands)
                seen["stage"] = stage_message
                seen["timeout"] = timeout_seconds
            return output

        return run

    def test_success_when_both_probes_answer(self):
        report = verify_split_deployment(
            self.PLAN,
            endpoint_url="http://54.1.2.3",
            run_commands=self._runner(
                "CLOUDWISE_SPLIT frontend=200 api=200"
            ),
        )

        self.assertEqual(report["status"], HEALTHY_STATUS)
        self.assertTrue(report["frontend"]["ok"])
        self.assertTrue(report["backend"]["ok"])
        self.assertEqual(report["backend"]["path"], "/api/v1/doctors")
        self.assertEqual(report["publicUrl"], "http://54.1.2.3")
        self.assertIn("checkedAt", report)
        self.assertIn("/api/v1", report["apiBasePaths"])

    def test_failure_when_backend_api_is_not_reachable(self):
        report = verify_split_deployment(
            self.PLAN,
            run_commands=self._runner("CLOUDWISE_SPLIT frontend=200 api=500"),
        )

        self.assertEqual(report["status"], FAILED_STATUS)
        self.assertTrue(report["frontend"]["ok"])
        self.assertFalse(report["backend"]["ok"])
        self.assertIn("backend API", report["message"])

    def test_empty_output_is_skipped_not_failed(self):
        report = verify_split_deployment(
            self.PLAN, run_commands=self._runner(""),
        )

        self.assertEqual(report["status"], SKIPPED_STATUS)

    def test_runner_exception_is_skipped_not_failed(self):
        def boom(commands, stage_message, timeout_seconds):
            raise RuntimeError("SSM unavailable")

        report = verify_split_deployment(self.PLAN, run_commands=boom)

        self.assertEqual(report["status"], SKIPPED_STATUS)
        self.assertIn("SSM unavailable", report["message"])

    def test_non_split_plan_returns_none(self):
        self.assertIsNone(verify_split_deployment({}, run_commands=self._runner("")))

    def test_probe_command_uses_discovered_path_and_localhost(self):
        command = build_probe_command("/api/v1/doctors")

        self.assertIn("http://127.0.0.1/api/v1/doctors", command)
        self.assertIn("CLOUDWISE_SPLIT", command)
        self.assertNotIn("localhost", command)

    def test_probe_command_falls_back_when_no_paths(self):
        command = build_probe_command(None)

        self.assertIn("http://127.0.0.1/api/health", command)

    def test_probe_command_rejects_unsafe_paths(self):
        command = build_probe_command("/api/x; rm -rf /")

        self.assertIn("http://127.0.0.1/api/health", command)

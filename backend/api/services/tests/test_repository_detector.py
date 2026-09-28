from django.test import SimpleTestCase

from api.services.deployment.repository_detector import (
    ARCHITECTURE_BACKEND_ONLY,
    ARCHITECTURE_FRONTEND_ONLY,
    ARCHITECTURE_SEPARATE,
    detect_repository,
)

# Structure mirrors https://github.com/Tirth-22/itue301-exam-24DCS047-5CSE1-B-batch
TARGET_REPO_FILES = {
    "README.md": (
        "# Hospital Appointment System\n\n"
        "Backend runs at http://localhost:5000\n"
    ),
    ".env.example": "MONGO_URI=your_mongodb_connection_string\n",
    "backend/package.json": (
        '{"name":"hospital-appointment-backend","main":"server.js",'
        '"scripts":{"start":"node server.js"},'
        '"dependencies":{"dotenv":"^16.6.1","express":"^5.1.0",'
        '"mongoose":"^8.18.0"}}'
    ),
    "backend/package-lock.json": "{}",
    "backend/server.js": (
        "require('dotenv').config()\n"
        "const express = require('express')\n"
        "const app = express()\n"
        "const PORT = process.env.PORT || 5000\n"
        "app.get('/api/v1/doctors', (req, res) => res.json({ ok: true }))\n"
        "app.get('/api/v1/appointments', (req, res) => res.json({ ok: true }))\n"
        "app.listen(PORT, () => console.log('listening on ' + PORT))\n"
    ),
    "frontend/package.json": (
        '{"name":"hospital-appointment-system","scripts":{'
        '"dev":"vite","build":"vite build"},'
        '"dependencies":{"react":"^19.2.8","react-dom":"^19.2.8",'
        '"react-router-dom":"^7.8.2"},'
        '"devDependencies":{"@vitejs/plugin-react":"^6.0.4",'
        '"vite":"^8.2.0"}}'
    ),
    "frontend/package-lock.json": "{}",
    "frontend/vite.config.js": (
        "import { defineConfig } from 'vite'\n"
        "import react from '@vitejs/plugin-react'\n"
        "export default defineConfig({ plugins: [react()] })\n"
    ),
    "frontend/src/App.jsx": (
        "<Routes>"
        '<Route path="/" element={<HomePage />} />'
        '<Route path="/doctors" element={<DoctorsPage />} />'
        '<Route path="/booking" element={<BookingPage />} />'
        "</Routes>"
    ),
    "frontend/src/pages/BookingPage.jsx": (
        "useEffect(() => { fetch('/api/v1/doctors') }, [])\n"
        "await fetch('/api/v1/appointments', { method: 'POST' })\n"
    ),
}


class TargetRepositoryDetectionTests(SimpleTestCase):
    """Phase 14 cases for the CloudWise exam repository."""

    def setUp(self):
        self.profile = detect_repository(TARGET_REPO_FILES)

    def test_classified_as_separate_frontend_backend(self):
        self.assertEqual(self.profile.architecture, ARCHITECTURE_SEPARATE)
        self.assertTrue(self.profile.requires_separate_frontend_backend)
        self.assertTrue(self.profile.supports_split_deployment)
        self.assertEqual(self.profile.application_type, "full-stack")

    def test_backend_port_detected_from_source_on_5000(self):
        backend = self.profile.backend

        self.assertEqual(backend.path, "backend")
        self.assertEqual(backend.runtime, "node")
        self.assertEqual(backend.port, 5000)
        self.assertEqual(backend.port_evidence, "source")

    def test_backend_start_command_is_npm_start(self):
        backend = self.profile.backend

        self.assertEqual(backend.start_script, "node server.js")
        self.assertEqual(backend.start_command, "npm start")
        self.assertEqual(backend.entry_file, "server.js")
        self.assertEqual(backend.package_manager, "npm")

    def test_frontend_profile(self):
        frontend = self.profile.frontend

        self.assertEqual(frontend.path, "frontend")
        self.assertEqual(frontend.technology, "React")
        self.assertEqual(frontend.framework, "vite")
        self.assertEqual(frontend.package_manager, "npm")
        self.assertEqual(frontend.install_command, "npm ci")
        self.assertEqual(frontend.build_command, "npm run build")
        self.assertEqual(frontend.output_directory, "dist")
        self.assertEqual(frontend.port, 80)

    def test_api_paths_exclude_spa_routes(self):
        self.assertEqual(self.profile.api_base_paths, ("/api/v1",))
        self.assertEqual(
            self.profile.api_probe_paths,
            ("/api/v1/doctors", "/api/v1/appointments"),
        )
        for route in ("/doctors", "/booking", "/"):
            self.assertNotIn(route, self.profile.api_probe_paths)

    def test_database_and_environment_labels(self):
        self.assertEqual(self.profile.database_type, "MongoDB")
        self.assertEqual(self.profile.required_env_vars, ("MONGO_URI",))
        self.assertEqual(self.profile.issues, ())

    def test_manifest_is_serialisable(self):
        manifest = self.profile.to_manifest()

        self.assertEqual(manifest["architecture"], ARCHITECTURE_SEPARATE)
        self.assertEqual(manifest["backend"]["port"], 5000)
        self.assertEqual(manifest["backend"]["startCommand"], "npm start")
        self.assertEqual(manifest["database"]["type"], "mongodb")
        self.assertEqual(manifest["requiredEnvVars"], ["MONGO_URI"])
        self.assertEqual(manifest["api"]["probePaths"][0], "/api/v1/doctors")


class ArchitectureGateTests(SimpleTestCase):
    """Only true split repositories are routed to the new adapter."""

    def test_root_frontend_repository_is_not_split(self):
        profile = detect_repository({
            "package.json": (
                '{"dependencies":{"react":"18.3.1"},'
                '"devDependencies":{"vite":"5.4.0"}}'
            ),
        })

        self.assertEqual(profile.architecture, ARCHITECTURE_FRONTEND_ONLY)
        self.assertFalse(profile.requires_separate_frontend_backend)
        self.assertIsNone(profile.frontend)
        self.assertIsNone(profile.backend)

    def test_root_backend_repository_is_not_split(self):
        profile = detect_repository({"requirements.txt": "flask==3.0.3\n"})

        self.assertEqual(profile.architecture, ARCHITECTURE_BACKEND_ONLY)
        self.assertFalse(profile.requires_separate_frontend_backend)

    def test_client_server_layout_is_split_with_default_port(self):
        profile = detect_repository({
            "client/package.json": (
                '{"dependencies":{"react":"18.3.1"},'
                '"devDependencies":{"vite":"5.4.0"}}'
            ),
            "server/package.json": '{"dependencies":{"express":"4.19.2"}}',
        })

        self.assertEqual(profile.architecture, ARCHITECTURE_SEPARATE)
        self.assertEqual(profile.frontend.path, "client")
        self.assertEqual(profile.backend.path, "server")
        self.assertEqual(profile.backend.port, 3000)
        self.assertEqual(profile.backend.port_evidence, "default")

    def test_frontend_without_backend_marker_is_not_split(self):
        profile = detect_repository({
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
        })

        self.assertFalse(profile.requires_separate_frontend_backend)


class BackendPortEvidenceTests(SimpleTestCase):
    """Port priority: Dockerfile → env → source → readme → default."""

    def test_dockerfile_expose_beats_source(self):
        profile = detect_repository({
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
            "backend/Dockerfile": "FROM node:20-alpine\nEXPOSE 9000\n",
            "backend/server.js": "require('express')().listen(4000)\n",
        })

        self.assertEqual(profile.backend.port, 9000)
        self.assertEqual(profile.backend.port_evidence, "dockerfile")

    def test_env_template_port_is_used(self):
        profile = detect_repository({
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
            "backend/.env.example": "PORT=7000\n",
        })

        self.assertEqual(profile.backend.port, 7000)
        self.assertEqual(profile.backend.port_evidence, "env")

    def test_readme_port_is_used_when_source_silent(self):
        profile = detect_repository({
            "backend/requirements.txt": "Django>=5.0\n",
            "README.md": "Run locally at http://localhost:5500\n",
        })

        self.assertEqual(profile.backend.port, 5500)
        self.assertEqual(profile.backend.port_evidence, "readme")

    def test_framework_defaults(self):
        node = detect_repository({
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
        })
        flask = detect_repository({
            "backend/requirements.txt": "flask==3.0.3\n",
        })
        django = detect_repository({
            "backend/requirements.txt": "Django>=5.0\n",
            "backend/manage.py": "print('hi')\n",
        })

        self.assertEqual(node.backend.port, 3000)
        self.assertEqual(node.backend.port_evidence, "default")
        self.assertEqual(flask.backend.port, 5000)
        self.assertEqual(flask.backend.port_evidence, "default")
        self.assertEqual(django.backend.port, 8000)
        self.assertEqual(django.backend.port_evidence, "default")

    def test_compose_env_port_is_detected(self):
        profile = detect_repository({
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
            "docker-compose.yml": (
                "services:\n  backend:\n    environment:\n"
                "      - PORT=6100\n"
            ),
        })

        self.assertEqual(profile.backend.port, 6100)
        self.assertEqual(profile.backend.port_evidence, "env")


class BackendReadinessIssueTests(SimpleTestCase):
    def test_missing_start_script_is_reported(self):
        profile = detect_repository({
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
        })

        self.assertIsNone(profile.backend.start_command)
        self.assertTrue(any(
            "no start script" in issue for issue in profile.issues
        ))

    def test_entry_file_fallback_when_start_script_missing(self):
        profile = detect_repository({
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "backend/package.json": '{"dependencies":{"express":"4.19.2"}}',
            "backend/index.js": "require('express')().listen(3001)\n",
        })

        self.assertEqual(profile.backend.start_command, "node index.js")
        self.assertEqual(profile.backend.entry_file, "index.js")

    def test_missing_frontend_build_script_is_reported(self):
        profile = detect_repository({
            "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
            "backend/package.json": (
                '{"scripts":{"start":"node server.js"}}'
            ),
            "backend/server.js": "require('http').createServer().listen(4000)\n",
        })

        self.assertIsNone(profile.frontend.build_command)
        self.assertTrue(any(
            "no build script" in issue for issue in profile.issues
        ))

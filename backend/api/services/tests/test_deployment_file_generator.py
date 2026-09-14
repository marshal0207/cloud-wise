from django.test import SimpleTestCase

from api.services.deployment_file_generator import generate_deployment_files


class DeploymentFileGeneratorTests(SimpleTestCase):
    def test_generates_spring_boot_files(self):
        result = generate_deployment_files(
            {"pom.xml": "<project></project>"}, provider="AWS"
        )

        self.assertEqual(result["technology"]["technology"], "SPRING_BOOT")
        self.assertIn("Dockerfile", result["files"])
        self.assertIn("docker-compose.yml", result["files"])
        self.assertIn(".github/workflows/deploy.yml", result["files"])
        self.assertIn("eclipse-temurin", result["files"]["Dockerfile"])
        self.assertIn("8080:8080", result["files"]["docker-compose.yml"])

    def test_generates_node_files(self):
        result = generate_deployment_files(
            {"package.json": '{"dependencies":{"express":"4.21.2"}}'},
            provider="AWS",
        )

        self.assertEqual(result["technology"]["technology"], "NODE_JS")
        self.assertIn("node:20-alpine", result["files"]["Dockerfile"])
        self.assertIn("3000:3000", result["files"]["docker-compose.yml"])

    def test_generates_python_files(self):
        result = generate_deployment_files(
            {"requirements.txt": "Django>=5.0"}, provider="AWS"
        )

        self.assertEqual(result["technology"]["technology"], "PYTHON")
        self.assertIn("python:3.13-slim", result["files"]["Dockerfile"])
        self.assertIn("8000:8000", result["files"]["docker-compose.yml"])

    def test_generates_react_files_and_provider_label(self):
        result = generate_deployment_files(
            {"package.json": '{"dependencies":{"react":"18.3.1"}}'},
            provider="GCP",
        )

        self.assertEqual(result["technology"]["technology"], "REACT")
        self.assertIn("nginx:alpine", result["files"]["Dockerfile"])
        self.assertIn("Target provider: GCP", result["files"][".github/workflows/deploy.yml"])

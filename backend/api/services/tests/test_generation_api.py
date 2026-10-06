from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase

User = get_user_model()


class DeploymentFileGenerationApiTests(APITestCase):
    url = "/api/deployment/generate-files"

    def setUp(self):
        self.user = User.objects.create_user(
            username="genuser",
            password="pass1234",
            email="gen@example.com",
        )
        self.client.force_authenticate(user=self.user)

    def test_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            self.url,
            {"provider": "AWS", "files": {"package.json": "{}"}},
            format="json",
        )
        self.assertIn(response.status_code, (401, 403))

    def test_generates_files_from_repository_metadata(self):
        response = self.client.post(
            self.url,
            {
                "provider": "AWS",
                "files": {
                    "package.json": '{"dependencies":{"react":"18.3.1"}}'
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(response.data["data"]["technology"]["technology"], "REACT")
        self.assertIn("Dockerfile", response.data["data"]["files"])
        self.assertIn("docker-compose.yml", response.data["data"]["files"])
        self.assertIn(
            ".github/workflows/deploy.yml",
            response.data["data"]["files"],
        )

    def test_returns_aws_ec2_deployment_plan_without_vercel_render(self):
        response = self.client.post(
            self.url,
            {
                "provider": "AWS",
                "files": {
                    "frontend/package.json": '{"dependencies":{"react":"18.3.1"}}',
                    "backend/pom.xml": (
                        "<project><dependency>"
                        "<groupId>org.springframework.boot</groupId>"
                        "<artifactId>spring-boot-starter-web</artifactId>"
                        "</dependency></project>"
                    ),
                },
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        plan = data["deploymentPlan"]

        self.assertEqual(plan["target"], "AWS_EC2")
        self.assertEqual(plan["containers"], ["frontend", "backend", "nginx"])
        self.assertTrue(plan["requiresNginx"])
        self.assertIn("nginx.conf", data["files"])
        self.assertNotIn("vercel.json", data["files"])
        self.assertNotIn("render.yaml", data["files"])
        self.assertEqual(data["detection"]["frontend"], "React")
        self.assertEqual(data["detection"]["backend"], "Spring Boot")

    def test_rejects_missing_repository_files(self):
        response = self.client.post(self.url, {"provider": "AWS"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

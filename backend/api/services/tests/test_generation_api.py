from rest_framework.test import APITestCase


class DeploymentFileGenerationApiTests(APITestCase):
    url = "/api/deployment/generate-files"

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

    def test_rejects_missing_repository_files(self):
        response = self.client.post(self.url, {"provider": "AWS"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

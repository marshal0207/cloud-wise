from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase


class GitHubOAuthApiTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="oauth-user",
            email="oauth@example.com",
            password="Passw0rd",
        )
        self.client.force_authenticate(user=self.user)

    @override_settings(GITHUB_CLIENT_ID="")
    def test_oauth_start_requires_server_configuration(self):
        response = self.client.get("/api/github/oauth/start")

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.data["success"])

    def test_oauth_callback_rejects_invalid_state(self):
        response = self.client.get(
            "/api/github/oauth/callback?code=example-code&state=invalid"
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

    def test_repository_listing_requires_github_connection(self):
        response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])

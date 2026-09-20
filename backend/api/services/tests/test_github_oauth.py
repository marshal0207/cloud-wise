import json
import urllib.error
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APITestCase

from api.models import GitHubConnection


class MockHTTPResponse:
    def __init__(self, body, status=200):
        self._body = body
        self.code = status

    def read(self):
        return self._body

    def decode(self):
        return self._body.decode('utf-8') if isinstance(self._body, bytes) else self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MockHTTPError(urllib.error.HTTPError):
    def __init__(self, code, body=b''):
        super().__init__('https://api.github.com/user/repos', code, 'Error', {}, None)
        self._body = body

    def read(self):
        return self._body


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

    def test_repository_listing_handles_401(self):
        GitHubConnection.objects.create(
            user=self.user,
            access_token="test-token",
            github_user_id="123",
            github_login="testuser",
        )
        with patch("api.views.urllib.request.urlopen", side_effect=MockHTTPError(401, b'{"message": "Unauthorized"}')):
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.data["success"])
        self.assertIn("invalid or expired", response.data["error"].lower())

    def test_repository_listing_handles_403(self):
        GitHubConnection.objects.create(
            user=self.user,
            access_token="test-token",
            github_user_id="123",
            github_login="testuser",
        )
        with patch("api.views.urllib.request.urlopen", side_effect=MockHTTPError(403, b'{"message": "Rate limit exceeded"}')):
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertIn("rate limit", response.data["error"].lower())

    def test_repository_listing_handles_404(self):
        GitHubConnection.objects.create(
            user=self.user,
            access_token="test-token",
            github_user_id="123",
            github_login="testuser",
        )
        with patch("api.views.urllib.request.urlopen", side_effect=MockHTTPError(404, b'{"message": "Not Found"}')):
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])
        self.assertIn("not found", response.data["error"].lower())

    def test_repository_listing_returns_repos_on_success(self):
        GitHubConnection.objects.create(
            user=self.user,
            access_token="test-token",
            github_user_id="123",
            github_login="testuser",
        )
        body = json.dumps([
            {"id": 1, "name": "test-repo", "full_name": "user/test-repo", "private": False, "default_branch": "main"}
        ]).encode()
        with patch("api.views.urllib.request.urlopen", return_value=MockHTTPResponse(body)):
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        self.assertEqual(len(response.data["data"]), 1)
        self.assertEqual(response.data["data"][0]["full_name"], "user/test-repo")

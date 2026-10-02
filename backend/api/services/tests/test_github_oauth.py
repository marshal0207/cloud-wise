import json
import urllib.error
import urllib.parse
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.core import signing
from django.test import override_settings
from rest_framework.test import APITestCase

from api.models import GitHubConnection
from api.views import GITHUB_OAUTH_STATE_SALT

TEST_CLIENT_ID = "test-client-id"
TEST_CLIENT_SECRET = "test-client-secret"
TEST_REDIRECT_URI = "http://localhost:8000/api/github/oauth/callback"
TEST_FRONTEND_URL = "http://localhost:5173"

GITHUB_OAUTH_TEST_SETTINGS = dict(
    GITHUB_CLIENT_ID=TEST_CLIENT_ID,
    GITHUB_CLIENT_SECRET=TEST_CLIENT_SECRET,
    GITHUB_REDIRECT_URI=TEST_REDIRECT_URI,
    GITHUB_OAUTH_SCOPES="repo workflow",
    FRONTEND_URL=TEST_FRONTEND_URL,
)


def make_state(user_id):
    return signing.dumps(
        {"uid": str(user_id), "nonce": "test-nonce"},
        salt=GITHUB_OAUTH_STATE_SALT,
    )


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

    def test_oauth_start_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/github/oauth/start")

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("detail", response.data)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["code"], "AUTH_REQUIRED")
        self.assertIn("sign in", response.data["error"].lower())

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_oauth_start_returns_signed_authorization_url(self):
        response = self.client.get("/api/github/oauth/start")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["success"])
        url = response.data["authorizationUrl"]
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "github.com")
        self.assertEqual(parsed.path, "/login/oauth/authorize")
        self.assertEqual(query["client_id"], [TEST_CLIENT_ID])
        self.assertEqual(query["redirect_uri"], [TEST_REDIRECT_URI])
        self.assertEqual(query["scope"], ["repo workflow"])
        self.assertEqual(query["response_type"], ["code"])

        payload = signing.loads(query["state"][0], salt=GITHUB_OAUTH_STATE_SALT)
        self.assertEqual(payload["uid"], str(self.user.pk))
        self.assertTrue(payload["nonce"])

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_oauth_start_state_is_bound_to_the_authenticated_user(self):
        other = get_user_model().objects.create_user(
            username="other-user-2",
            email="other2@example.com",
            password="Passw0rd",
        )
        self.client.force_authenticate(user=other)
        state = urllib.parse.parse_qs(
            urllib.parse.urlparse(
                self.client.get("/api/github/oauth/start").data["authorizationUrl"]
            ).query
        )["state"][0]

        payload = signing.loads(state, salt=GITHUB_OAUTH_STATE_SALT)

        self.assertEqual(payload["uid"], str(other.pk))

    @override_settings(GITHUB_CLIENT_ID="", GITHUB_CLIENT_SECRET="")
    def test_oauth_start_lists_missing_variables(self):
        response = self.client.get("/api/github/oauth/start")

        self.assertEqual(response.status_code, 503)
        self.assertIn("GITHUB_CLIENT_ID", response.data["error"])
        self.assertIn("GITHUB_CLIENT_SECRET", response.data["error"])

    def test_oauth_callback_rejects_state_signed_with_other_salt(self):
        state = signing.dumps({"uid": str(self.user.pk)}, salt="wrong.salt")

        response = self.client.get(
            f"/api/github/oauth/callback?code=example-code&state={urllib.parse.quote(state)}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "STATE_INVALID")

    @override_settings(GITHUB_OAUTH_STATE_MAX_AGE=-1)
    def test_oauth_callback_rejects_expired_state(self):
        response = self.client.get(
            f"/api/github/oauth/callback?code=example-code&state={urllib.parse.quote(make_state(self.user.pk))}"
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["code"], "STATE_EXPIRED")

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_oauth_callback_redirects_on_github_denial(self):
        response = self.client.get(
            "/api/github/oauth/callback?error=access_denied&error_description=The+user+has+denied+your+application"
        )

        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertTrue(location.startswith(TEST_FRONTEND_URL + "/generate"))
        self.assertIn("github=error", location)
        self.assertIn("github_detail=access_denied", location)
        self.assertFalse(GitHubConnection.objects.filter(user=self.user).exists())

    @override_settings(GITHUB_CLIENT_ID="", GITHUB_CLIENT_SECRET="")
    def test_oauth_callback_reports_missing_configuration(self):
        response = self.client.get(
            f"/api/github/oauth/callback?code=example-code&state={urllib.parse.quote(make_state(self.user.pk))}"
        )

        self.assertEqual(response.status_code, 503)
        self.assertFalse(response.data["success"])
        self.assertIn("GITHUB_CLIENT_SECRET", response.data["error"])

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_oauth_callback_reports_invalid_authorization_code(self):
        body = json.dumps(
            {"error": "bad_verification_code", "error_description": "The code passed is incorrect or expired."}
        ).encode()
        with patch("api.views.urllib.request.urlopen", return_value=MockHTTPResponse(body)):
            response = self.client.get(
                f"/api/github/oauth/callback?code=bad-code&state={urllib.parse.quote(make_state(self.user.pk))}"
            )

        self.assertEqual(response.status_code, 302)
        self.assertIn("github=error", response["Location"])
        self.assertIn("github_detail=invalid_code", response["Location"])
        self.assertNotIn(TEST_CLIENT_SECRET, response.content.decode())
        self.assertFalse(GitHubConnection.objects.filter(user=self.user).exists())

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_oauth_callback_exchanges_code_and_stores_encrypted_token(self):
        token_body = json.dumps(
            {"access_token": "gho_real_secret_token", "token_type": "bearer", "scope": "repo,workflow"}
        ).encode()
        profile_body = json.dumps({"id": 987654, "login": "octo-alice"}).encode()

        with patch(
            "api.views.urllib.request.urlopen",
            side_effect=[MockHTTPResponse(token_body), MockHTTPResponse(profile_body)],
        ) as mocked:
            response = self.client.get(
                f"/api/github/oauth/callback?code=real-code&state={urllib.parse.quote(make_state(self.user.pk))}"
            )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith(TEST_FRONTEND_URL + "/generate?github=connected"))
        self.assertNotIn(TEST_CLIENT_SECRET, response.content.decode())

        token_request = mocked.call_args_list[0].args[0]
        token_payload = token_request.data.decode()
        self.assertIn("code=real-code", token_payload)
        self.assertIn(f"redirect_uri={urllib.parse.quote(TEST_REDIRECT_URI, safe='')}", token_payload)
        self.assertIn(f"client_secret={TEST_CLIENT_SECRET}", token_payload)

        connection = GitHubConnection.objects.get(user=self.user)
        self.assertNotEqual(connection.access_token, "gho_real_secret_token")
        self.assertEqual(connection.get_token(), "gho_real_secret_token")
        self.assertEqual(connection.github_login, "octo-alice")
        self.assertEqual(connection.github_user_id, "987654")
        self.assertEqual(connection.status, "connected")
        self.assertIn("repo", connection.scopes)
        self.assertIn("workflow", connection.scopes)

    def test_repository_inspect_route_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.post("/api/github/repos/owner/repository/inspect", {}, format="json")

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("detail", response.data)
        self.assertFalse(response.data["success"])

    def test_repository_listing_requires_authentication(self):
        self.client.force_authenticate(user=None)

        response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 401)
        self.assertNotIn("detail", response.data)
        self.assertFalse(response.data["success"])


class GitHubOAuthUserIsolationTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.alice = User.objects.create_user(
            username="alice", email="alice@example.com", password="Passw0rd"
        )
        self.bob = User.objects.create_user(
            username="bob", email="bob@example.com", password="Passw0rd"
        )

    def _connect(self, user, github_id, github_login, token):
        token_body = json.dumps(
            {"access_token": token, "token_type": "bearer", "scope": "repo"}
        ).encode()
        profile_body = json.dumps({"id": github_id, "login": github_login}).encode()

        with patch(
            "api.views.urllib.request.urlopen",
            side_effect=[MockHTTPResponse(token_body), MockHTTPResponse(profile_body)],
        ):
            self.client.get(
                f"/api/github/oauth/callback?code=code-{github_login}"
                f"&state={urllib.parse.quote(make_state(user.pk))}"
            )

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_each_cloudwise_user_stores_their_own_github_token(self):
        self._connect(self.alice, 111, "alice-gh", "gho_alice_token")
        self._connect(self.bob, 222, "bob-gh", "gho_bob_token")

        alice_conn = GitHubConnection.objects.get(user=self.alice)
        bob_conn = GitHubConnection.objects.get(user=self.bob)

        self.assertEqual(alice_conn.get_token(), "gho_alice_token")
        self.assertEqual(bob_conn.get_token(), "gho_bob_token")
        self.assertNotEqual(alice_conn.get_token(), bob_conn.get_token())
        self.assertEqual(alice_conn.github_login, "alice-gh")
        self.assertEqual(bob_conn.github_login, "bob-gh")
        self.assertEqual(alice_conn.github_user_id, "111")
        self.assertEqual(bob_conn.github_user_id, "222")
        self.assertNotEqual(alice_conn.access_token, bob_conn.access_token)

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_reconnecting_replaces_only_that_users_token(self):
        self._connect(self.alice, 111, "alice-gh", "gho_alice_token_v1")
        self._connect(self.bob, 222, "bob-gh", "gho_bob_token")
        self._connect(self.alice, 111, "alice-gh", "gho_alice_token_v2")

        self.assertEqual(GitHubConnection.objects.filter(user=self.alice).count(), 1)
        self.assertEqual(
            GitHubConnection.objects.get(user=self.alice).get_token(),
            "gho_alice_token_v2",
        )
        self.assertEqual(
            GitHubConnection.objects.get(user=self.bob).get_token(),
            "gho_bob_token",
        )

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_repository_listing_sends_only_the_current_users_token(self):
        self._connect(self.alice, 111, "alice-gh", "gho_alice_token")
        self._connect(self.bob, 222, "bob-gh", "gho_bob_token")

        self.client.force_authenticate(user=self.bob)
        with patch(
            "api.views.urllib.request.urlopen",
            return_value=MockHTTPResponse(b"[]"),
        ) as mocked:
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 200)
        sent_request = mocked.call_args.args[0]
        sent_headers = dict(sent_request.header_items())
        self.assertEqual(sent_headers.get("Authorization"), "Bearer gho_bob_token")
        self.assertNotIn("gho_alice_token", str(sent_headers))

        self.client.force_authenticate(user=self.alice)
        with patch(
            "api.views.urllib.request.urlopen",
            return_value=MockHTTPResponse(b"[]"),
        ) as mocked:
            response = self.client.get("/api/github/repos")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            dict(mocked.call_args.args[0].header_items()).get("Authorization"),
            "Bearer gho_alice_token",
        )

    @override_settings(**GITHUB_OAUTH_TEST_SETTINGS)
    def test_identity_comes_from_signed_state_not_client(self):
        self._connect(self.alice, 111, "alice-gh", "gho_alice_token")

        self.assertTrue(GitHubConnection.objects.filter(user=self.alice).exists())
        self.assertFalse(GitHubConnection.objects.filter(user=self.bob).exists())


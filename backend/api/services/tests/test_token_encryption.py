from django.contrib.auth import get_user_model
from django.test import TestCase

from api.models import GitHubConnection
from api.services.token_encryption import decrypt_token, encrypt_token


class TokenEncryptionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='token-user',
            email='token@example.com',
            password='Passw0rd',
        )

    def test_encrypted_token_round_trips(self):
        for token in (
            'gho_real_github_token_value',
            'ghp_personal_access_token_value',
            'github_pat_0000000000_abcdefghijklmnopqrstuvwxyz',
            'a-token-with-no-recognizable-prefix',
        ):
            cipher = encrypt_token(token)

            self.assertNotEqual(cipher, token)
            self.assertNotIn(token, cipher)
            self.assertEqual(decrypt_token(cipher), token)

    def test_legacy_plaintext_tokens_still_return_themselves(self):
        for token in ('test-token', 'server-token', 'gho_legacy_plaintext', 'x'):
            self.assertEqual(decrypt_token(token), token)

    def test_empty_token_is_unchanged(self):
        self.assertEqual(encrypt_token(''), '')
        self.assertEqual(decrypt_token(''), '')

    def test_ciphertext_is_not_mistaken_for_plaintext(self):
        # Regression test: older Fernet versions used ':'-separated segments and
        # the previous implementation sniffed the token's shape to decide whether
        # it was ciphertext. Modern Fernet tokens contain no ':' at all, so any
        # shape-based heuristic silently stopped decrypting stored tokens.
        cipher = encrypt_token('gho_somebody_github_token')

        self.assertEqual(cipher.count(':'), 0)
        self.assertEqual(decrypt_token(cipher), 'gho_somebody_github_token')

    def test_model_stores_ciphertext_and_returns_plaintext(self):
        connection = GitHubConnection.objects.create(
            user=self.user,
            github_user_id='4242',
            github_login='token-user',
        )
        connection.set_token('gho_model_level_token')
        connection.save()

        connection.refresh_from_db()

        self.assertNotEqual(connection.access_token, 'gho_model_level_token')
        self.assertEqual(connection.get_token(), 'gho_model_level_token')

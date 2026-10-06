"""
Token Encryption Service

Provides symmetric encryption for OAuth tokens using Fernet.
Derives an encryption key from GITHUB_TOKEN_ENCRYPTION_KEY or settings.SECRET_KEY.
Supports backward-compatibility with legacy unencrypted tokens.
"""

import base64
import hashlib
import logging

from django.conf import settings

logger = logging.getLogger(__name__)

try:
    from cryptography.fernet import Fernet, InvalidToken
except ImportError:  # pragma: no cover - depends on the deployed environment
    Fernet = None

    class InvalidToken(Exception):
        """Stand-in raised when `cryptography` is unavailable."""


def get_encryption_fernet() -> Fernet:
    """Derive a URL-safe base64-encoded 32-byte key for Fernet from configuration."""
    if Fernet is None:
        raise RuntimeError(
            "The 'cryptography' package is not installed. "
            "Run `pip install -r requirements.txt` to enable GitHub token encryption."
        )
    raw_key = getattr(settings, 'GITHUB_TOKEN_ENCRYPTION_KEY', None) or settings.SECRET_KEY
    digest = hashlib.sha256(raw_key.encode('utf-8')).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)


def encrypt_token(plain_token: str) -> str:
    """Encrypt a plaintext OAuth token."""
    if not plain_token:
        return ""
    try:
        f = get_encryption_fernet()
        return f.encrypt(plain_token.encode('utf-8')).decode('utf-8')
    except Exception as exc:
        logger.error("Failed to encrypt GitHub token: %s", exc)
        return plain_token


def decrypt_token(cipher_token: str) -> str:
    """Decrypt an encrypted OAuth token. Transparently handles legacy plaintext tokens.

    Always attempt Fernet decryption first: a stored value either decrypts with the
    configured key or it is a legacy plaintext token (or was written with a different
    key) — in which case Fernet raises InvalidToken and the original value is returned.
    Guessing from the token's shape is unsafe: Fernet's token format has changed
    between releases, so a valid ciphertext is not reliably recognizable.
    """
    if not cipher_token:
        return ""
    if Fernet is None:
        logger.error(
            "Cannot decrypt stored GitHub token: 'cryptography' is not installed. "
            "Install requirements.txt before using stored connections."
        )
        return cipher_token

    try:
        return get_encryption_fernet().decrypt(
            cipher_token.encode('utf-8')
        ).decode('utf-8')
    except InvalidToken:
        # Not a Fernet token encrypted with the current key: either a legacy
        # plaintext token stored before encryption existed, or the encryption
        # key changed since the token was stored.
        return cipher_token
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Unexpected error decrypting GitHub token: %s", exc)
        return cipher_token

"""Symmetric encryption for secrets stored in the database."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _fernet() -> Fernet:
    master = get_settings().secret_key().encode()
    # Derive a stable 32-byte key from the master secret.
    digest = hashlib.sha256(b"nexus-secret-store:" + master).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def hint_for(secret: str) -> str:
    return f"…{secret[-4:]}" if len(secret) >= 8 else "…"

"""Authenticated encryption (Fernet) for camera/SMTP secrets.

Key comes from CAMERA_CREDENTIAL_ENCRYPTION_KEY or ..._FILE, never from the DB.
Losing the key makes stored secrets unrecoverable (re-enter them); see docs/SECURITY.md."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken


class SecretError(Exception):
    pass


class SecretBox:
    def __init__(self, key: str) -> None:
        if not key:
            raise SecretError("CAMERA_CREDENTIAL_ENCRYPTION_KEY is not set (generate with `make gen-key`)")
        try:
            self._f = Fernet(key.encode())
        except ValueError as exc:
            raise SecretError("encryption key is not a valid Fernet key") from exc

    def encrypt(self, plaintext: str) -> str:
        return self._f.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        try:
            return self._f.decrypt(token.encode()).decode()
        except InvalidToken as exc:
            raise SecretError("cannot decrypt secret: wrong key or corrupted value") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode()

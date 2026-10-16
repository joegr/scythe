"""Encrypt GitHub tokens at rest with a local Fernet key."""

from functools import lru_cache

from cryptography.fernet import Fernet

from .config import ROOT, settings

SECRET_FILE = ROOT / ".scythe-secret"


@lru_cache
def _fernet() -> Fernet:
    key = settings.secret_key
    if not key:
        if SECRET_FILE.exists():
            key = SECRET_FILE.read_text().strip()
        else:
            key = Fernet.generate_key().decode()
            SECRET_FILE.write_text(key)
            SECRET_FILE.chmod(0o600)
    return Fernet(key.encode())


def encrypt(value: str) -> bytes:
    return _fernet().encrypt(value.encode())


def decrypt(value: bytes) -> str:
    return _fernet().decrypt(value).decode()

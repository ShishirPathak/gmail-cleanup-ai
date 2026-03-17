from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from typing import Any

import jwt
from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    key = sha256(settings.secret_key.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str | None) -> str | None:
    if not value:
        return None
    return _fernet().decrypt(value.encode("utf-8")).decode("utf-8")


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    expires_delta = timedelta(
        minutes=expires_minutes or settings.token_expiry_minutes
    )
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + expires_delta,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.secret_key, algorithms=["HS256"])

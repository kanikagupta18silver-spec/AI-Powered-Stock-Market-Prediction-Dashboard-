"""Password hashing and signed access tokens using the Python standard library."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from typing import Any

TOKEN_ISSUER = "stock-market-dashboard"
TOKEN_LIFETIME_SECONDS = 60 * 60 * 24
PASSWORD_ITERATIONS = 310_000
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_email(email: str) -> str:
    normalized = email.strip().lower()
    if len(normalized) > 254 or not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address.")
    return normalized


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, password_hash: str) -> bool:
    try:
        algorithm, iterations, salt, expected = password_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256" or int(iterations) != PASSWORD_ITERATIONS:
            return False
        expected_digest = base64.urlsafe_b64decode(expected.encode("ascii"))
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            base64.urlsafe_b64decode(salt.encode("ascii")),
            PASSWORD_ITERATIONS,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected_digest)


def _encode_part(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, separators=(",", ":"), sort_keys=True).encode()
    return base64.urlsafe_b64encode(encoded).rstrip(b"=").decode("ascii")


def create_access_token(user: dict[str, Any], secret: str) -> str:
    issued_at = int(time.time())
    header = _encode_part({"alg": "HS256", "typ": "JWT"})
    payload = _encode_part(
        {
            "sub": str(user["id"]),
            "email": user["email"],
            "iss": TOKEN_ISSUER,
            "iat": issued_at,
            "exp": issued_at + TOKEN_LIFETIME_SECONDS,
        }
    )
    message = f"{header}.{payload}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{header}.{payload}.{encoded_signature}"


def decode_access_token(token: str, secret: str) -> dict[str, Any]:
    try:
        header_part, payload_part, signature_part = token.split(".")
        message = f"{header_part}.{payload_part}".encode("ascii")
        expected = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).digest()
        provided = base64.urlsafe_b64decode(
            signature_part + "=" * (-len(signature_part) % 4)
        )
        if not hmac.compare_digest(expected, provided):
            raise ValueError("Invalid bearer token.")

        header = json.loads(
            base64.urlsafe_b64decode(header_part + "=" * (-len(header_part) % 4))
        )
        payload = json.loads(
            base64.urlsafe_b64decode(payload_part + "=" * (-len(payload_part) % 4))
        )
        if (
            header.get("alg") != "HS256"
            or payload.get("iss") != TOKEN_ISSUER
            or not isinstance(payload.get("sub"), str)
            or int(payload["exp"]) <= int(time.time())
        ):
            raise ValueError("Invalid or expired bearer token.")
        return payload
    except (KeyError, TypeError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("Invalid bearer token.") from error
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("Invalid or expired bearer token.") from error

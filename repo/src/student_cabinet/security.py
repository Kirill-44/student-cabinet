"""Хэширование паролей и подписанные токены (только стандартная библиотека)."""

import base64
import hashlib
import hmac
import secrets
import time

from .errors import AuthError

_ITERATIONS = 200_000


def hash_password(password):
    """Возвращает строку вида pbkdf2$<iter>$<salt>$<hash>."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), _ITERATIONS)
    return f"pbkdf2${_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password, stored):
    try:
        _, iters, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iters))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(digest.hex(), expected)


def _b64(data):
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _sign(secret, payload):
    return _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest())


def make_token(secret, user_id, ttl_seconds, now=None):
    """Токен формата <user_id>.<expires>.<signature>."""
    expires = int((now if now is not None else time.time()) + ttl_seconds)
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(secret, payload)}"


def read_token(secret, token, now=None):
    """Возвращает user_id или бросает AuthError."""
    try:
        user_id, expires, signature = token.split(".")
        payload = f"{user_id}.{expires}"
        ok = hmac.compare_digest(signature, _sign(secret, payload))
        alive = int(expires) >= (now if now is not None else time.time())
        uid = int(user_id)
    except (ValueError, AttributeError):
        raise AuthError("Некорректный токен")
    if not ok:
        raise AuthError("Подпись токена неверна")
    if not alive:
        raise AuthError("Срок действия токена истёк")
    return uid

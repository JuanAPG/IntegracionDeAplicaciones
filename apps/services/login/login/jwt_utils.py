"""
apps/services/login/login/jwt_utils.py
JWT generation and authentication token management.

Uses PyJWT with a shared secret (JWT_SECRET) loaded from the root .env.
The token includes claims: sub (user_id), email, role, iat, exp.
Expiration defaults to 1 hour (configurable via JWT_EXPIRATION_HOURS).
"""
from datetime import datetime, timedelta, timezone

import jwt

from . import config


def generate_jwt(user_id, email, role):
    """Generate a signed JWT token for the authenticated user.

    Returns the token string. Claims:
        sub  — user ID (standard JWT subject)
        email — user's email address
        role  — user role (admin/user)
        iat  — issued at (UTC)
        exp  — expiration (UTC)
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=config.JWT_EXPIRATION_HOURS),
    }
    token = jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)
    # PyJWT >= 2.x returns str; ensure consistent type
    if isinstance(token, bytes):
        token = token.decode("utf-8")
    return token


def verify_jwt(token):
    """Verify a JWT token and return its payload.

    Raises:
        jwt.ExpiredSignatureError — token has expired
        jwt.InvalidTokenError — token is invalid (bad signature, malformed, etc.)
    """
    return jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])

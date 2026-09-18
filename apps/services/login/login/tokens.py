"""
apps/services/login/login/tokens.py
Tokens de verificacion de correo: se entrega el valor en claro una sola
vez (dentro del enlace enviado por sendmail) y en la base solo se guarda
su hash SHA-256. Asi, leer la tabla no permite verificar cuentas.
"""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import config


def issue_token():
    """Devuelve (token_en_claro, token_hash, expiracion_utc)."""
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=config.TOKEN_TTL_HOURS)
    return raw, digest, expires_at


def hash_token(raw):
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()

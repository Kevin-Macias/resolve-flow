"""Passwords use Argon2id; high-entropy opaque tokens use domain-separated hashes."""

import asyncio
import hashlib
import os
import secrets
from typing import Literal

from fastapi import HTTPException
from pwdlib import PasswordHash

PASSWORDS = PasswordHash.recommended()
DUMMY_HASH = PASSWORDS.hash("resolveflow-dummy-not-a-user-password")


def auth_mode() -> Literal["demo", "password"]:
    mode = os.getenv("AUTH_MODE", "password")
    if mode not in ("demo", "password"):
        raise HTTPException(503, "Authentication unavailable")
    return mode


def new_token(kind: Literal["invitation", "session"]) -> str:
    return ("rfi_" if kind == "invitation" else "rfs_") + secrets.token_urlsafe(32)


def token_hash(kind: Literal["invitation", "session"], token: str) -> str:
    return hashlib.sha256(f"resolveflow:{kind}:{token}".encode()).hexdigest()


async def hash_password(password: str) -> str:
    return await asyncio.to_thread(PASSWORDS.hash, password)


async def verify_password(password: str, stored: str) -> bool:
    try:
        return await asyncio.to_thread(PASSWORDS.verify, password, stored)
    except (ValueError, TypeError):
        return False

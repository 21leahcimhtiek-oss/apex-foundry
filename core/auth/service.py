"""Auth service — tenants, users, JWT tokens, per-tenant usage metering.

Tenants and users live in the pluggable MemoryStore (in-memory dev,
Redis prod) so auth follows the same swappable-backend rule as the rest
of the platform. Passwords use PBKDF2-HMAC-SHA256 (stdlib). Tokens are
JWTs signed with APP_SECRET_KEY.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from typing import Any

import jwt

from core.kernel.memory.store import MemoryStore

STORE_KEY = "auth:directory"
JWT_ALG = "HS256"
TOKEN_TTL_SECONDS = 24 * 3600

# Daily request allowances per plan (mirrors MONETIZATION.md).
PLAN_LIMITS: dict[str, int] = {"free": 10, "pro": 5_000, "enterprise": 100_000}


def _hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"pbkdf2${salt}${digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, _ = stored.split("$", 2)
    except ValueError:
        return False
    return secrets.compare_digest(_hash_password(password, salt), stored)


class AuthService:
    def __init__(self, store: MemoryStore) -> None:
        self.store = store

    # ── directory ────────────────────────────────────────────────
    def _directory(self) -> dict[str, Any]:
        return self.store.get(STORE_KEY) or {"tenants": {}, "users": {}}

    def _save(self, directory: dict[str, Any]) -> None:
        self.store.set(STORE_KEY, directory)

    # ── registration / login ─────────────────────────────────────
    def register_tenant(
        self, tenant_name: str, email: str, password: str, plan: str = "free"
    ) -> dict[str, Any]:
        directory = self._directory()
        if email in directory["users"]:
            raise ValueError("email already registered")
        tenant_id = f"tnt_{secrets.token_hex(8)}"
        directory["tenants"][tenant_id] = {
            "tenant_id": tenant_id,
            "name": tenant_name,
            "plan": plan,
            "created_at": int(time.time()),
        }
        directory["users"][email] = {
            "email": email,
            "tenant_id": tenant_id,
            "password": _hash_password(password),
            "role": "admin",
        }
        self._save(directory)
        return directory["users"][email]

    def add_user(
        self, tenant_id: str, email: str, password: str, role: str = "member"
    ) -> dict[str, Any]:
        directory = self._directory()
        if tenant_id not in directory["tenants"]:
            raise KeyError("tenant not found")
        if email in directory["users"]:
            raise ValueError("email already registered")
        directory["users"][email] = {
            "email": email,
            "tenant_id": tenant_id,
            "password": _hash_password(password),
            "role": role,
        }
        self._save(directory)
        return directory["users"][email]

    def authenticate(self, email: str, password: str) -> dict[str, Any]:
        user = self._directory()["users"].get(email)
        if user is None or not _verify_password(password, user["password"]):
            raise ValueError("invalid credentials")
        return user

    # ── tokens ───────────────────────────────────────────────────
    @staticmethod
    def _secret() -> str:
        return os.getenv("APP_SECRET_KEY", "change-this-in-production")

    def create_token(self, email: str) -> str:
        user = self._directory()["users"][email]
        now = int(time.time())
        return jwt.encode(
            {
                "sub": email,
                "tenant_id": user["tenant_id"],
                "role": user["role"],
                "iat": now,
                "exp": now + TOKEN_TTL_SECONDS,
            },
            self._secret(),
            algorithm=JWT_ALG,
        )

    def decode_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(token, self._secret(), algorithms=[JWT_ALG])

    # ── tenancy + metering ───────────────────────────────────────
    def set_plan(self, tenant_id: str, plan: str) -> dict[str, Any]:
        """Set a tenant's plan (called by the billing webhook / downgrade)."""
        if plan not in PLAN_LIMITS:
            raise ValueError(f"Unknown plan: {plan}")
        directory = self._directory()
        tenant = directory["tenants"].get(tenant_id)
        if tenant is None:
            raise KeyError("tenant not found")
        tenant["plan"] = plan
        self._save(directory)
        return tenant

    def get_tenant(self, tenant_id: str) -> dict[str, Any]:
        tenant = self._directory()["tenants"].get(tenant_id)
        if tenant is None:
            raise KeyError("tenant not found")
        return tenant

    def usage_key(self, tenant_id: str) -> str:
        return f"usage:{tenant_id}:{time.strftime('%Y-%m-%d')}"

    def check_and_increment_usage(self, tenant_id: str) -> dict[str, Any]:
        """Count one request; raise PermissionError over plan allowance."""
        tenant = self.get_tenant(tenant_id)
        limit = PLAN_LIMITS.get(tenant["plan"], PLAN_LIMITS["free"])
        used = int(self.store.get(self.usage_key(tenant_id)) or 0)
        if used >= limit:
            raise PermissionError(
                f"Daily request limit reached for plan '{tenant['plan']}' "
                f"({limit}/day). Upgrade to continue."
            )
        self.store.set(self.usage_key(tenant_id), used + 1)
        return {"used": used + 1, "limit": limit, "plan": tenant["plan"]}

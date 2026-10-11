"""Warehouse (Postgres) settings loaded from environment variables (D79).

Three profiles, no DSN: `admin` (POSTGRES_USER/POSTGRES_PASSWORD, only for `pits db migrate`),
`loader` and `reader`. Only the requested profiles are validated, so the loader does not
need the admin password.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from pits.warehouse.errors import WarehouseConfigError

DEFAULT_DB = "pits_warehouse"
DEFAULT_PORT = 5433
MIN_PASSWORD_LENGTH = 16
LOADER_ROLE = "pits_loader"
READER_ROLE = "pits_reader"
OWNER_ROLE = "pits_owner"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class Profile(StrEnum):
    ADMIN = "admin"
    LOADER = "loader"
    READER = "reader"


@dataclass(frozen=True)
class WarehouseSettings:
    """Where to connect and with which credentials; passwords never appear in repr."""

    host: str
    port: int
    dbname: str
    admin_user: str | None = None
    admin_password: str | None = field(default=None, repr=False)
    loader_password: str | None = field(default=None, repr=False)
    reader_password: str | None = field(default=None, repr=False)

    def credentials(self, profile: Profile) -> tuple[str, str]:
        """Return (user, password) for `profile`; raises if it was not loaded."""
        if profile is Profile.ADMIN:
            user, password = self.admin_user, self.admin_password
        elif profile is Profile.LOADER:
            user, password = LOADER_ROLE, self.loader_password
        else:
            user, password = READER_ROLE, self.reader_password
        if not user or not password:
            raise WarehouseConfigError(f"Credentials for profile '{profile.value}' not loaded")
        return user, password


def _get(env: Mapping[str, str], name: str) -> str:
    return env.get(name, "").strip()


def _password(env: Mapping[str, str], name: str, *, min_length: int = MIN_PASSWORD_LENGTH) -> str:
    value = env.get(name, "")  # not stripped: surrounding whitespace is rejected, not removed
    if not value.strip():
        raise WarehouseConfigError(f"Missing required environment variable: {name}")
    if value != value.strip():
        raise WarehouseConfigError(f"{name} must not have leading or trailing whitespace")
    if len(value) < min_length:
        raise WarehouseConfigError(f"{name} must be at least {min_length} characters")
    return value


def load_warehouse_settings(
    env: Mapping[str, str], profiles: Iterable[Profile] = (Profile.LOADER,)
) -> WarehouseSettings:
    """Build WarehouseSettings from `env`; error messages never include values."""
    wanted = set(profiles)
    if not wanted:
        raise WarehouseConfigError("At least one profile is required")

    host = _get(env, "PITS_PG_HOST") or "127.0.0.1"
    if host not in _LOOPBACK_HOSTS:
        raise WarehouseConfigError(
            "PITS_PG_HOST must be a loopback host (127.0.0.1, localhost, ::1)"
        )

    raw_port = _get(env, "POSTGRES_HOST_PORT") or str(DEFAULT_PORT)
    if not raw_port.isascii() or not raw_port.isdigit():
        raise WarehouseConfigError("POSTGRES_HOST_PORT must be an integer")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise WarehouseConfigError("POSTGRES_HOST_PORT must be between 1 and 65535")
    if port == 5432:
        raise WarehouseConfigError(
            "POSTGRES_HOST_PORT must not be 5432 (reserved for native Postgres)"
        )

    dbname = _get(env, "PITS_WAREHOUSE_DB") or DEFAULT_DB
    if not _IDENT_RE.match(dbname):
        raise WarehouseConfigError("PITS_WAREHOUSE_DB must match ^[a-z][a-z0-9_]{0,62}$")

    admin_user = admin_password = loader_password = reader_password = None
    if Profile.ADMIN in wanted:
        admin_user = _get(env, "POSTGRES_USER")
        if not admin_user:
            raise WarehouseConfigError("Missing required environment variable: POSTGRES_USER")
        admin_password = _password(env, "POSTGRES_PASSWORD", min_length=1)
    if Profile.LOADER in wanted:
        loader_password = _password(env, "PITS_PG_LOADER_PASSWORD")
    if Profile.READER in wanted:
        reader_password = _password(env, "PITS_PG_READER_PASSWORD")

    return WarehouseSettings(
        host=host,
        port=port,
        dbname=dbname,
        admin_user=admin_user,
        admin_password=admin_password,
        loader_password=loader_password,
        reader_password=reader_password,
    )

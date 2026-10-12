"""Warehouse (Postgres) settings loaded from environment variables (D79).

Four profiles, no DSN: `admin` (POSTGRES_USER/POSTGRES_PASSWORD, only for `pits db migrate`),
`loader`, `reader` and `transformer` (dbt, D86). Only the requested profiles are validated,
so the loader does not need the admin password.
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
TRANSFORMER_ROLE = "pits_transformer"
OWNER_ROLE = "pits_owner"

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})
# D91: closed allow-list (not configurable). `postgres` is the compose service name, reachable
# only on the internal network (Airflow containers); loopback is the host-side dev default.
_COMPOSE_HOST = "postgres"
_ALLOWED_HOSTS = _LOOPBACK_HOSTS | {_COMPOSE_HOST}
_IDENT_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


@dataclass(frozen=True)
class RoleNames:
    """Cluster-level role names. Defaults are the real ones; tests inject suffixed names."""

    owner: str = OWNER_ROLE
    loader: str = LOADER_ROLE
    reader: str = READER_ROLE
    transformer: str = TRANSFORMER_ROLE

    def __post_init__(self) -> None:
        for name in (self.owner, self.loader, self.reader, self.transformer):
            if not _IDENT_RE.match(name):
                raise WarehouseConfigError("Role names must match ^[a-z][a-z0-9_]{0,62}$")


class Profile(StrEnum):
    ADMIN = "admin"
    LOADER = "loader"
    READER = "reader"
    TRANSFORMER = "transformer"


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
    transformer_password: str | None = field(default=None, repr=False)
    roles: RoleNames = field(default_factory=RoleNames)

    def credentials(self, profile: Profile) -> tuple[str, str]:
        """Return (user, password) for `profile`; raises if it was not loaded."""
        if profile is Profile.ADMIN:
            user, password = self.admin_user, self.admin_password
        elif profile is Profile.LOADER:
            user, password = self.roles.loader, self.loader_password
        elif profile is Profile.READER:
            user, password = self.roles.reader, self.reader_password
        else:
            user, password = self.roles.transformer, self.transformer_password
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
    if host not in _ALLOWED_HOSTS:
        raise WarehouseConfigError(
            "PITS_PG_HOST must be a loopback host (127.0.0.1, localhost, ::1) or 'postgres'"
        )

    raw_port = _get(env, "POSTGRES_HOST_PORT") or str(DEFAULT_PORT)
    if not raw_port.isascii() or not raw_port.isdigit():
        raise WarehouseConfigError("POSTGRES_HOST_PORT must be an integer")
    port = int(raw_port)
    if not 1 <= port <= 65535:
        raise WarehouseConfigError("POSTGRES_HOST_PORT must be between 1 and 65535")
    if port == 5432 and host != _COMPOSE_HOST:
        raise WarehouseConfigError(
            "POSTGRES_HOST_PORT must not be 5432 with a loopback host (native Postgres port)"
        )

    dbname = _get(env, "PITS_WAREHOUSE_DB") or DEFAULT_DB
    if not _IDENT_RE.match(dbname):
        raise WarehouseConfigError("PITS_WAREHOUSE_DB must match ^[a-z][a-z0-9_]{0,62}$")

    admin_user = admin_password = loader_password = reader_password = None
    transformer_password = None
    if Profile.ADMIN in wanted:
        admin_user = _get(env, "POSTGRES_USER")
        if not admin_user:
            raise WarehouseConfigError("Missing required environment variable: POSTGRES_USER")
        admin_password = _password(env, "POSTGRES_PASSWORD", min_length=1)
    if Profile.LOADER in wanted:
        loader_password = _password(env, "PITS_PG_LOADER_PASSWORD")
    if Profile.READER in wanted:
        reader_password = _password(env, "PITS_PG_READER_PASSWORD")
    if Profile.TRANSFORMER in wanted:
        transformer_password = _password(env, "PITS_PG_TRANSFORMER_PASSWORD")

    return WarehouseSettings(
        host=host,
        port=port,
        dbname=dbname,
        admin_user=admin_user,
        admin_password=admin_password,
        loader_password=loader_password,
        reader_password=reader_password,
        transformer_password=transformer_password,
    )

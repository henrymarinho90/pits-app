"""SODA settings loaded from environment variables."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlparse

DEFAULT_BASE_URL = "https://www.datos.gov.co"

_TOKEN_RE = re.compile(r"[!-~]+")


class SodaConfigError(ValueError):
    """Raised when the SODA configuration is invalid."""


@dataclass(frozen=True)
class SodaSettings:
    """Connection settings for a Socrata portal; the app token is optional."""

    base_url: str = DEFAULT_BASE_URL
    app_token: str | None = field(default=None, repr=False)


def load_soda_settings(env: Mapping[str, str]) -> SodaSettings:
    """Build SodaSettings from `env`; error messages never include values."""
    base_url = env.get("SODA_BASE_URL", "").strip() or DEFAULT_BASE_URL
    token = env.get("SODA_APP_TOKEN", "").strip() or None

    if token is not None and not _TOKEN_RE.fullmatch(token):
        raise SodaConfigError("SODA_APP_TOKEN contains invalid characters")

    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise SodaConfigError("SODA_BASE_URL must be an http(s) URL with a host")
    if parsed.username is not None or parsed.password is not None:
        raise SodaConfigError("SODA_BASE_URL must not embed credentials")

    if token is not None and parsed.scheme != "https":
        raise SodaConfigError("SODA_APP_TOKEN requires an https SODA_BASE_URL")

    return SodaSettings(base_url=base_url.rstrip("/"), app_token=token)

"""Error types shared by the normalizers (TRM, RUNT)."""

from __future__ import annotations

__all__ = ["NormalizeError", "NormalizePermanentError", "NormalizeTransientError"]


class NormalizeError(RuntimeError):
    """Base class of normalize failures."""


class NormalizePermanentError(NormalizeError):
    """Retrying cannot help (bad data, conflict, too large, missing full batch)."""


class NormalizeTransientError(NormalizeError):
    """Network/store failure: the same command may succeed later."""

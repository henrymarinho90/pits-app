"""normalize_common is the single home of the normalize error types (TRM re-exports them)."""

from __future__ import annotations

from pits.sources import normalize_common
from pits.sources.runt import normalize as runt_normalize
from pits.sources.trm import normalize as trm_normalize


def test_trm_and_runt_share_the_same_error_classes():
    for name in ("NormalizeError", "NormalizePermanentError", "NormalizeTransientError"):
        assert getattr(trm_normalize, name) is getattr(normalize_common, name)
    assert runt_normalize.NormalizePermanentError is normalize_common.NormalizePermanentError
    assert runt_normalize.NormalizeTransientError is normalize_common.NormalizeTransientError


def test_hierarchy():
    assert issubclass(normalize_common.NormalizePermanentError, normalize_common.NormalizeError)
    assert issubclass(normalize_common.NormalizeTransientError, normalize_common.NormalizeError)

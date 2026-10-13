"""Retention of Airflow task logs (D109): pure, testable logic; the DAG only calls it.

Deletes regular `*.log` files older than `max_age_days` under the logs root and then the
directories left empty (bottom-up, never the root). Symlinks are never followed nor deleted
through: a symlinked file or directory is skipped, and a root that is a symlink is rejected.
"""

from __future__ import annotations

import os
import stat
import time
from dataclasses import dataclass
from pathlib import Path

LOGS_ROOT = Path("/opt/airflow/logs")
MAX_AGE_DAYS = 30


@dataclass(frozen=True)
class RetentionResult:
    deleted_files: int
    freed_bytes: int
    removed_dirs: int


def purge_old_logs(
    root: Path,
    *,
    max_age_days: int = MAX_AGE_DAYS,
    now: float | None = None,
    allowed_root: Path = LOGS_ROOT,
) -> RetentionResult:
    """Delete old `*.log` files and empty dirs under `root`; ValueError if root is invalid."""
    root = Path(root)
    if root != allowed_root:
        raise ValueError(f"log retention root must be {allowed_root}, got {root}")
    if root.is_symlink():
        raise ValueError(f"log retention root must not be a symlink: {root}")
    if not root.is_dir():
        raise ValueError(f"log retention root is not a directory: {root}")

    cutoff = (time.time() if now is None else now) - max_age_days * 86400
    deleted_files = freed_bytes = removed_dirs = 0

    # topdown=False + followlinks=False: children before parents, symlinked dirs not entered.
    for dirpath, _dirnames, filenames in os.walk(root, topdown=False, followlinks=False):
        directory = Path(dirpath)
        for name in filenames:
            if not name.endswith(".log"):
                continue
            path = directory / name
            info = path.lstat()  # lstat: a symlink is reported as a symlink, not its target
            if not stat.S_ISREG(info.st_mode) or info.st_mtime >= cutoff:
                continue
            path.unlink()
            deleted_files += 1
            freed_bytes += info.st_size
        if directory == root:
            continue
        if directory.is_symlink():
            continue
        try:
            directory.rmdir()  # only succeeds if empty: never removes content
        except OSError:
            continue
        removed_dirs += 1
    return RetentionResult(deleted_files, freed_bytes, removed_dirs)

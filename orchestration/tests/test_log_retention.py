import os
from pathlib import Path

import pytest

from pits_cli.log_retention import LOGS_ROOT, RetentionResult, purge_old_logs

NOW = 2_000_000_000.0
DAY = 86400


def make_file(path: Path, size: int, age_days: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    mtime = NOW - age_days * DAY
    os.utime(path, (mtime, mtime))
    return path


def purge(root: Path, **kwargs) -> RetentionResult:
    return purge_old_logs(root, now=NOW, allowed_root=root, **kwargs)


def test_old_logs_deleted_new_kept(tmp_path):
    old = make_file(tmp_path / "dag_id=a" / "run" / "old.log", 10, 31)
    new = make_file(tmp_path / "dag_id=a" / "run" / "new.log", 10, 29)
    result = purge(tmp_path)
    assert not old.exists()
    assert new.exists()
    assert result == RetentionResult(deleted_files=1, freed_bytes=10, removed_dirs=0)


def test_exactly_at_cutoff_is_kept(tmp_path):
    keep = make_file(tmp_path / "edge.log", 5, 30)
    assert purge(tmp_path).deleted_files == 0
    assert keep.exists()


def test_non_log_files_untouched_even_if_old(tmp_path):
    other = make_file(tmp_path / "x" / "old.txt", 7, 90)
    log_like = make_file(tmp_path / "x" / "old.log.gz", 7, 90)
    result = purge(tmp_path)
    assert other.exists() and log_like.exists()
    assert result == RetentionResult(0, 0, 0)


def test_symlinks_are_not_followed(tmp_path):
    outside = tmp_path / "outside"
    victim = make_file(outside / "victim.log", 9, 90)
    root = tmp_path / "logs"
    root.mkdir()
    (root / "link.log").symlink_to(victim)
    (root / "linkdir").symlink_to(outside, target_is_directory=True)
    result = purge(root)
    assert victim.exists()
    assert (root / "link.log").is_symlink() and (root / "linkdir").is_symlink()
    assert result == RetentionResult(0, 0, 0)


def test_empty_dirs_removed_bottom_up_and_root_kept(tmp_path):
    make_file(tmp_path / "a" / "b" / "c" / "old.log", 3, 40)
    (tmp_path / "empty").mkdir()
    keep = make_file(tmp_path / "k" / "new.log", 3, 1)
    result = purge(tmp_path)
    assert result == RetentionResult(deleted_files=1, freed_bytes=3, removed_dirs=4)
    assert not (tmp_path / "a").exists() and not (tmp_path / "empty").exists()
    assert keep.exists() and tmp_path.is_dir()


def test_directory_with_non_log_content_is_kept(tmp_path):
    make_file(tmp_path / "d" / "old.log", 3, 40)
    other = make_file(tmp_path / "d" / "notes.txt", 3, 40)
    result = purge(tmp_path)
    assert other.exists()
    assert result == RetentionResult(1, 3, 0)


def test_empty_root_stays(tmp_path):
    assert purge(tmp_path) == RetentionResult(0, 0, 0)
    assert tmp_path.is_dir()


def test_counts_accumulate(tmp_path):
    make_file(tmp_path / "a" / "1.log", 100, 31)
    make_file(tmp_path / "b" / "2.log", 50, 60)
    make_file(tmp_path / "b" / "3.log", 1, 1)
    assert purge(tmp_path) == RetentionResult(2, 150, 1)


def test_root_other_than_logs_is_rejected(tmp_path):
    make_file(tmp_path / "old.log", 1, 90)
    with pytest.raises(ValueError, match="must be"):
        purge_old_logs(tmp_path, now=NOW)  # default allowed_root is /opt/airflow/logs
    assert (tmp_path / "old.log").exists()
    assert LOGS_ROOT == Path("/opt/airflow/logs")


def test_symlink_root_is_rejected(tmp_path):
    real = tmp_path / "real"
    make_file(real / "old.log", 1, 90)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        purge_old_logs(link, now=NOW, allowed_root=link)
    assert (real / "old.log").exists()


def test_missing_root_is_rejected(tmp_path):
    missing = tmp_path / "nope"
    with pytest.raises(ValueError, match="not a directory"):
        purge_old_logs(missing, now=NOW, allowed_root=missing)

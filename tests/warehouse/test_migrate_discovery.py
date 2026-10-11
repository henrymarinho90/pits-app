import hashlib

import pytest

from pits.warehouse.errors import WarehousePermanentError
from pits.warehouse.migrate import MigrationError, discover_migrations, render
from pits.warehouse.settings import RoleNames


def _write(root, name, text="SELECT 1;\n"):
    (root / name).write_bytes(text.encode())


def test_packaged_directory_is_discoverable():
    # The .gitkeep must be ignored; whatever is shipped must be a valid set.
    found = discover_migrations()
    assert [m.version for m in found] == list(range(1, len(found) + 1))


def test_orders_by_version_and_hashes_raw_bytes(tmp_path):
    _write(tmp_path, "0002_second.sql", "SELECT 2;\n")
    _write(tmp_path, "0001_first.sql", "SELECT 1;\r\n")
    _write(tmp_path, ".gitkeep", "")
    found = discover_migrations(tmp_path)
    assert [(m.version, m.name, m.filename) for m in found] == [
        (1, "first", "0001_first.sql"),
        (2, "second", "0002_second.sql"),
    ]
    assert found[0].sha256 == hashlib.sha256(b"SELECT 1;\r\n").hexdigest()


def test_empty_directory(tmp_path):
    assert discover_migrations(tmp_path) == []


@pytest.mark.parametrize(
    "name",
    [
        "1_x.sql",
        "0001-x.sql",
        "0001_X.sql",
        "0001_.sql",
        "0001_x.SQL",
        "0001_x.sql.bak",
        "notes.txt",
    ],
)
def test_rejects_invalid_names(tmp_path, name):
    _write(tmp_path, name)
    with pytest.raises(MigrationError, match="Invalid migration entry name"):
        discover_migrations(tmp_path)


def test_rejects_gap(tmp_path):
    _write(tmp_path, "0001_a.sql")
    _write(tmp_path, "0003_c.sql")
    with pytest.raises(MigrationError, match="contiguous"):
        discover_migrations(tmp_path)


def test_must_start_at_one(tmp_path):
    _write(tmp_path, "0002_b.sql")
    with pytest.raises(MigrationError, match="contiguous"):
        discover_migrations(tmp_path)


def test_rejects_duplicate_version(tmp_path):
    _write(tmp_path, "0001_a.sql")
    _write(tmp_path, "0001_b.sql")
    with pytest.raises(MigrationError, match="Duplicate"):
        discover_migrations(tmp_path)


def test_rejects_non_utf8(tmp_path):
    (tmp_path / "0001_a.sql").write_bytes(b"\xff\xfe\x00")
    with pytest.raises(MigrationError, match="UTF-8"):
        discover_migrations(tmp_path)


def test_directory_with_sql_name_is_rejected(tmp_path):
    (tmp_path / "0001_a.sql").mkdir()
    with pytest.raises(MigrationError):
        discover_migrations(tmp_path)


def test_migration_error_is_permanent():
    assert issubclass(MigrationError, WarehousePermanentError)


def test_render_substitutes_quoted_roles(tmp_path):
    _write(
        tmp_path,
        "0001_a.sql",
        "GRANT SELECT ON t TO {{reader_role}}; -- {{owner_role}} {{loader_role}}",
    )
    (migration,) = discover_migrations(tmp_path)
    text = render(migration, RoleNames(owner="o_1", loader="l_1", reader="r_1"))
    assert text == 'GRANT SELECT ON t TO "r_1"; -- "o_1" "l_1"'
    # The recorded hash is over the raw file, not the rendered text.
    assert migration.sha256 == hashlib.sha256(migration.sql.encode()).hexdigest()


def test_role_names_are_validated():
    with pytest.raises(ValueError):
        RoleNames(owner='x"; DROP')

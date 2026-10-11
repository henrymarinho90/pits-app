import pytest

from pits.warehouse.bootstrap import RUN_LOCK_KEY, bootstrap
from pits.warehouse.connection import connect
from pits.warehouse.errors import WarehousePermanentError, WarehouseTransientError
from pits.warehouse.migrate import MIGRATE_LOCK_KEY, MigrationError, run_migrate
from pits.warehouse.settings import Profile

SQL_1 = (
    "CREATE TABLE ops.t_one (id int PRIMARY KEY);\nGRANT SELECT ON ops.t_one TO {{reader_role}};\n"
)
SQL_2 = "CREATE TABLE landing.t_two (id int PRIMARY KEY);\n"


@pytest.fixture
def migrations(tmp_path):
    (tmp_path / "0001_one.sql").write_text(SQL_1)
    return tmp_path


def _admin(settings):
    return connect(settings, Profile.ADMIN, autocommit=True)


def test_migrate_twice_applies_then_skips(pg_settings, migrations):
    (migrations / "0002_two.sql").write_text(SQL_2)
    first = run_migrate(pg_settings, migrations)
    assert (first.applied, first.skipped) == (2, 0)
    second = run_migrate(pg_settings, migrations)
    assert (second.applied, second.skipped) == (0, 2)
    with _admin(pg_settings) as conn:
        rows = conn.execute(
            "SELECT version, name, length(sha256) FROM ops.schema_migration ORDER BY 1"
        ).fetchall()
        owner = conn.execute(
            "SELECT pg_get_userbyid(relowner) FROM pg_class WHERE oid = 'ops.t_one'::regclass"
        ).fetchone()
    assert rows == [(1, "one", 64), (2, "two", 64)]
    assert owner == (pg_settings.roles.owner,)  # SET ROLE: created objects belong to the owner


def test_incremental_apply_only_runs_new_files(pg_settings, migrations):
    assert run_migrate(pg_settings, migrations).applied == 1
    (migrations / "0002_two.sql").write_text(SQL_2)
    result = run_migrate(pg_settings, migrations)
    assert (result.applied, result.skipped) == (1, 1)


def test_placeholder_and_default_privileges_reach_reader(pg_settings, migrations):
    (migrations / "0002_two.sql").write_text(SQL_2)
    run_migrate(pg_settings, migrations)
    reader = connect(pg_settings, Profile.READER, autocommit=True)
    try:
        assert reader.execute("SELECT count(*) FROM ops.t_one").fetchone() == (0,)
        assert reader.execute("SELECT count(*) FROM landing.t_two").fetchone() == (0,)
    finally:
        reader.close()


def test_failed_migration_rolls_back_and_is_not_recorded(pg_settings, migrations):
    run_migrate(pg_settings, migrations)
    (migrations / "0002_bad.sql").write_text("CREATE TABLE landing.half (id int);\nSELECT 1/0;\n")
    with pytest.raises(WarehousePermanentError):
        run_migrate(pg_settings, migrations)
    with _admin(pg_settings) as conn:
        assert conn.execute("SELECT to_regclass('landing.half')").fetchone() == (None,)
        assert conn.execute("SELECT count(*) FROM ops.schema_migration").fetchone() == (1,)


def test_changed_applied_migration_is_rejected(pg_settings, migrations):
    run_migrate(pg_settings, migrations)
    (migrations / "0001_one.sql").write_text(SQL_1 + "-- edited\n")
    with pytest.raises(MigrationError, match="changed after being applied"):
        run_migrate(pg_settings, migrations)


def test_applied_migration_missing_from_package_is_rejected(
    pg_settings, migrations, tmp_path_factory
):
    run_migrate(pg_settings, migrations)
    with pytest.raises(MigrationError, match="not in the package"):
        run_migrate(pg_settings, tmp_path_factory.mktemp("empty"))


def test_lock_held_is_transient_then_succeeds(pg_settings, migrations):
    run_migrate(pg_settings, migrations)
    (migrations / "0002_two.sql").write_text(SQL_2)
    holder = _admin(pg_settings)
    holder.execute("SELECT pg_advisory_lock(%s)", (MIGRATE_LOCK_KEY,))
    try:
        with pytest.raises(WarehouseTransientError):
            run_migrate(pg_settings, migrations)
    finally:
        holder.close()  # releases the session lock
    assert run_migrate(pg_settings, migrations).applied == 1


def test_roles_have_least_privilege_attributes(pg_settings):
    bootstrap(pg_settings)
    r = pg_settings.roles
    with _admin(pg_settings) as conn:
        rows = {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, rolinherit, "
                "rolreplication, rolbypassrls, rolconnlimit FROM pg_roles WHERE rolname = ANY(%s)",
                ([r.owner, r.loader, r.reader, r.transformer],),
            )
        }
        verifiers = dict(
            conn.execute(
                "SELECT rolname, rolpassword FROM pg_authid WHERE rolname = ANY(%s)",
                ([r.owner, r.loader, r.reader, r.transformer],),
            ).fetchall()
        )
    # login, super, createdb, createrole, inherit, replication, bypassrls, connlimit
    assert rows[r.owner] == (False, False, False, False, False, False, False, -1)
    assert rows[r.loader] == (True, False, False, False, False, False, False, -1)
    assert rows[r.reader] == (True, False, False, False, False, False, False, -1)
    assert rows[r.transformer] == (True, False, False, False, False, False, False, -1)
    assert verifiers[r.owner] is None
    for role, password in (
        (r.loader, pg_settings.loader_password),
        (r.reader, pg_settings.reader_password),
        (r.transformer, pg_settings.transformer_password),
    ):
        assert verifiers[role].startswith("SCRAM-SHA-256$")
        assert password not in verifiers[role]


def test_bootstrap_is_idempotent_and_baseline_is_correct(pg_settings):
    bootstrap(pg_settings)
    bootstrap(pg_settings)
    r = pg_settings.roles
    with _admin(pg_settings) as conn:
        db = conn.execute(
            "SELECT pg_get_userbyid(datdba), has_database_privilege(%s, datname, 'CONNECT'), "
            "has_database_privilege(%s, datname, 'TEMPORARY'), "
            "has_database_privilege(%s, datname, 'TEMPORARY'), "
            "has_database_privilege('public', datname, 'CONNECT') "
            "FROM pg_database WHERE datname = current_database()",
            (r.loader, r.loader, r.reader),
        ).fetchone()
        schemas = conn.execute(
            "SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace "
            "WHERE nspname IN ('ops', 'landing', 'staging', 'intermediate', 'marts') ORDER BY 1"
        ).fetchall()
        public_usage = conn.execute(
            "SELECT has_schema_privilege('public', 'public', 'CREATE')"
        ).fetchone()
        table_owner = conn.execute(
            "SELECT tableowner FROM pg_tables WHERE schemaname = 'ops' "
            "AND tablename = 'schema_migration'"
        ).fetchone()
    assert db == (r.owner, True, True, False, False)
    assert schemas == [
        (name, r.owner) for name in ("intermediate", "landing", "marts", "ops", "staging")
    ]
    assert public_usage == (False,)
    assert table_owner == (r.owner,)


def test_loader_and_reader_can_log_in_but_not_create(pg_settings):
    bootstrap(pg_settings)
    for profile in (Profile.LOADER, Profile.READER):
        conn = connect(pg_settings, profile, autocommit=True)
        try:
            can_create = conn.execute(
                "SELECT has_schema_privilege(current_user, 'ops', 'CREATE'), "
                "has_schema_privilege(current_user, 'landing', 'CREATE'), "
                "has_table_privilege(current_user, 'ops.schema_migration', 'SELECT')"
            ).fetchone()
        finally:
            conn.close()
        assert can_create == (False, False, False)


def test_run_lock_busy_is_transient_and_bootstrap_does_not_run(pg_settings, migrations):
    run_migrate(pg_settings, migrations)
    r = pg_settings.roles
    query = "SELECT rolpassword FROM pg_authid WHERE rolname = %s"
    with _admin(pg_settings) as conn:
        before = conn.execute(query, (r.loader,)).fetchone()
    holder = connect(pg_settings, Profile.ADMIN, dbname="postgres", autocommit=True)
    holder.execute("SELECT pg_advisory_lock(%s)", (RUN_LOCK_KEY,))
    try:
        with pytest.raises(WarehouseTransientError):
            run_migrate(pg_settings, migrations)
        with pytest.raises(WarehouseTransientError):
            bootstrap(pg_settings)
    finally:
        holder.close()
    with _admin(pg_settings) as conn:
        # A re-run of the bootstrap would have rotated the SCRAM salt.
        assert conn.execute(query, (r.loader,)).fetchone() == before
    assert run_migrate(pg_settings, migrations).skipped == 1

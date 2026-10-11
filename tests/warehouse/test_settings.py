import pytest

from pits.warehouse.errors import WarehouseConfigError
from pits.warehouse.settings import Profile, load_warehouse_settings

SENTINEL_LOADER = "sentinel-loader-pw-0123456789"
SENTINEL_READER = "sentinel-reader-pw-0123456789"
SENTINEL_ADMIN = "sentinel-admin-pw-0123456789"

BASE_ENV = {
    "PITS_PG_LOADER_PASSWORD": SENTINEL_LOADER,
    "PITS_PG_READER_PASSWORD": SENTINEL_READER,
    "POSTGRES_USER": "pits",
    "POSTGRES_PASSWORD": SENTINEL_ADMIN,
}
ALL = tuple(Profile)


def test_defaults():
    s = load_warehouse_settings(BASE_ENV, ALL)
    assert (s.host, s.port, s.dbname) == ("127.0.0.1", 5433, "pits_warehouse")
    assert s.credentials(Profile.ADMIN) == ("pits", SENTINEL_ADMIN)
    assert s.credentials(Profile.LOADER) == ("pits_loader", SENTINEL_LOADER)
    assert s.credentials(Profile.READER) == ("pits_reader", SENTINEL_READER)


def test_overrides():
    env = {
        **BASE_ENV,
        "PITS_PG_HOST": "localhost",
        "POSTGRES_HOST_PORT": "55000",
        "PITS_WAREHOUSE_DB": "pits_test_ab12cd34",
    }
    s = load_warehouse_settings(env, ALL)
    assert (s.host, s.port, s.dbname) == ("localhost", 55000, "pits_test_ab12cd34")


def test_loader_profile_does_not_need_admin_or_reader():
    s = load_warehouse_settings({"PITS_PG_LOADER_PASSWORD": SENTINEL_LOADER})
    assert s.credentials(Profile.LOADER)[0] == "pits_loader"
    with pytest.raises(WarehouseConfigError):
        s.credentials(Profile.ADMIN)


@pytest.mark.parametrize("host", ["0.0.0.0", "db.example.com", "10.0.0.5", "127.0.0.1.evil.com"])
def test_rejects_non_loopback_host(host):
    with pytest.raises(WarehouseConfigError, match="loopback"):
        load_warehouse_settings({**BASE_ENV, "PITS_PG_HOST": host}, ALL)


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "::1"])
def test_accepts_loopback_hosts(host):
    assert load_warehouse_settings({**BASE_ENV, "PITS_PG_HOST": host}, ALL).host == host


@pytest.mark.parametrize("port", ["5432", "0", "65536", "abc", "-1", "54 33"])
def test_rejects_bad_port(port):
    with pytest.raises(WarehouseConfigError, match="POSTGRES_HOST_PORT"):
        load_warehouse_settings({**BASE_ENV, "POSTGRES_HOST_PORT": port}, ALL)


@pytest.mark.parametrize("name", ["Pits", "1db", "a-b", "x;drop", "a" * 64])
def test_rejects_bad_db_name(name):
    with pytest.raises(WarehouseConfigError, match="PITS_WAREHOUSE_DB"):
        load_warehouse_settings({**BASE_ENV, "PITS_WAREHOUSE_DB": name}, ALL)


@pytest.mark.parametrize(
    ("variable", "profile"),
    [
        ("PITS_PG_LOADER_PASSWORD", Profile.LOADER),
        ("PITS_PG_READER_PASSWORD", Profile.READER),
    ],
)
@pytest.mark.parametrize("value", ["", "   ", "short-pw-15-chr"])
def test_rejects_missing_or_short_password(variable, profile, value):
    with pytest.raises(WarehouseConfigError, match=variable) as info:
        load_warehouse_settings({**BASE_ENV, variable: value}, [profile])
    assert value.strip() == "" or value not in str(info.value)


def test_admin_password_only_needs_to_be_non_empty():
    s = load_warehouse_settings({**BASE_ENV, "POSTGRES_PASSWORD": "change-me"}, [Profile.ADMIN])
    assert s.credentials(Profile.ADMIN) == ("pits", "change-me")
    for value in ("", "   "):
        with pytest.raises(WarehouseConfigError, match="POSTGRES_PASSWORD"):
            load_warehouse_settings({**BASE_ENV, "POSTGRES_PASSWORD": value}, [Profile.ADMIN])


@pytest.mark.parametrize(
    ("variable", "profile"),
    [
        ("PITS_PG_LOADER_PASSWORD", Profile.LOADER),
        ("PITS_PG_READER_PASSWORD", Profile.READER),
        ("POSTGRES_PASSWORD", Profile.ADMIN),
    ],
)
@pytest.mark.parametrize("template", [" {}", "{} ", "{}\n"])
def test_rejects_surrounding_whitespace_without_leaking(variable, profile, template):
    value = template.format("sentinel-ws-pw-0123456789")
    with pytest.raises(WarehouseConfigError, match=variable) as info:
        load_warehouse_settings({**BASE_ENV, variable: value}, [profile])
    assert "sentinel-ws-pw" not in str(info.value)


def test_password_of_exactly_16_is_accepted():
    pw = "x" * 16
    s = load_warehouse_settings({"PITS_PG_LOADER_PASSWORD": pw})
    assert s.credentials(Profile.LOADER)[1] == pw


def test_missing_admin_user():
    env = {k: v for k, v in BASE_ENV.items() if k != "POSTGRES_USER"}
    with pytest.raises(WarehouseConfigError, match="POSTGRES_USER"):
        load_warehouse_settings(env, [Profile.ADMIN])


def test_requires_a_profile():
    with pytest.raises(WarehouseConfigError):
        load_warehouse_settings(BASE_ENV, [])


def test_repr_and_str_hide_passwords():
    s = load_warehouse_settings(BASE_ENV, ALL)
    text = repr(s) + str(s)
    for secret in (SENTINEL_LOADER, SENTINEL_READER, SENTINEL_ADMIN):
        assert secret not in text


def test_errors_never_contain_secrets():
    env = {**BASE_ENV, "PITS_PG_HOST": "evil.example.com"}
    with pytest.raises(WarehouseConfigError) as info:
        load_warehouse_settings(env, ALL)
    for secret in (SENTINEL_LOADER, SENTINEL_READER, SENTINEL_ADMIN):
        assert secret not in str(info.value)

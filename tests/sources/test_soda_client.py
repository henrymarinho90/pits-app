"""Offline tests for the SODA settings and client (httpx.MockTransport, fake sleep)."""

from __future__ import annotations

import json

import httpx
import pytest

from pits.sources.soda.client import (
    MAX_ATTEMPTS,
    SodaClient,
    SodaPermanentError,
    SodaTransientError,
)
from pits.sources.soda.settings import (
    DEFAULT_BASE_URL,
    SodaConfigError,
    SodaSettings,
    load_soda_settings,
)

TOKEN = "s3cr3t-token-value"
ROWS = [{"valor": "3900.5", "vigenciadesde": "2026-10-10T00:00:00.000"}]


@pytest.fixture
def make_client():
    created: list[SodaClient] = []

    def _make(handler, token=TOKEN, jitter=lambda: 0.0):
        sleeps: list[float] = []
        client = SodaClient(
            SodaSettings(base_url="https://example.test", app_token=token),
            transport=httpx.MockTransport(handler),
            sleep=sleeps.append,
            jitter=jitter,
        )
        created.append(client)
        return client, sleeps

    yield _make
    for c in created:
        c.close()


def test_get_page_url_params_and_exact_bytes(make_client):
    seen: list[httpx.Request] = []
    body = json.dumps(ROWS).encode()

    def handler(request):
        seen.append(request)
        return httpx.Response(200, content=body)

    client, _ = make_client(handler)
    page = client.get_page("abcd-1234", {"$limit": 1000, "$offset": 0, "$order": "vigenciadesde"})
    assert page.body == body
    assert page.rows == ROWS
    url = seen[0].url
    assert url.host == "example.test"
    assert url.path == "/resource/abcd-1234.json"
    assert dict(url.params) == {"$limit": "1000", "$offset": "0", "$order": "vigenciadesde"}


def test_get_metadata(make_client):
    seen: list[httpx.Request] = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"rowsUpdatedAt": 1, "columns": []})

    client, _ = make_client(handler)
    assert client.get_metadata("abcd-1234")["rowsUpdatedAt"] == 1
    assert seen[0].url.path == "/api/views/abcd-1234.json"


def test_token_header_present_and_absent(make_client):
    headers: list[httpx.Headers] = []

    def handler(request):
        headers.append(request.headers)
        return httpx.Response(200, json=[])

    make_client(handler)[0].get_page("abcd-1234", {})
    make_client(handler, token=None)[0].get_page("abcd-1234", {})
    assert headers[0]["X-App-Token"] == TOKEN
    assert "X-App-Token" not in headers[1]


def test_429_retry_after_is_respected_then_succeeds(make_client):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "7"})
        return httpx.Response(200, json=ROWS)

    client, sleeps = make_client(handler)
    assert client.get_page("abcd-1234", {}).rows == ROWS
    assert sleeps == [7.0]


@pytest.mark.parametrize("exc", [httpx.ConnectError("boom"), httpx.ReadTimeout("slow")])
def test_transport_errors_are_retried(exc, make_client):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) < 3:
            raise exc
        return httpx.Response(200, json=ROWS)

    client, sleeps = make_client(handler)
    assert client.get_page("abcd-1234", {}).rows == ROWS
    assert sleeps == [1.0, 2.0]


def test_transport_error_exhausted_is_transient(make_client):
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    client, _ = make_client(handler)
    with pytest.raises(SodaTransientError, match="ConnectTimeout"):
        client.get_page("abcd-1234", {})


@pytest.mark.parametrize("status", [400, 403, 404])
def test_permanent_errors_do_not_retry(status, make_client):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    client, sleeps = make_client(handler)
    with pytest.raises(SodaPermanentError, match=str(status)):
        client.get_page("abcd-1234", {})
    assert len(calls) == 1
    assert sleeps == []


def test_invalid_json_and_wrong_shape_are_permanent(make_client):
    client, _ = make_client(lambda r: httpx.Response(200, content=b"<html>"))
    with pytest.raises(SodaPermanentError, match="not valid JSON"):
        client.get_page("abcd-1234", {})


def test_token_never_in_exceptions_or_repr(make_client):
    client, _ = make_client(lambda r: httpx.Response(503))
    with pytest.raises(SodaTransientError) as transient:
        client.get_page("abcd-1234", {})
    client, _ = make_client(lambda r: httpx.Response(404))
    with pytest.raises(SodaPermanentError) as permanent:
        client.get_metadata("abcd-1234")
    settings = SodaSettings(app_token=TOKEN)
    for text in (str(transient.value), str(permanent.value), repr(client), repr(settings)):
        assert TOKEN not in text


def test_settings_defaults_and_empty_token():
    settings = load_soda_settings({})
    assert settings.base_url == DEFAULT_BASE_URL
    assert settings.app_token is None
    assert load_soda_settings({"SODA_APP_TOKEN": "  "}).app_token is None
    assert load_soda_settings({"SODA_APP_TOKEN": TOKEN}).app_token == TOKEN


def test_settings_custom_base_url_strips_trailing_slash():
    assert load_soda_settings({"SODA_BASE_URL": "http://localhost:8080/"}).base_url == (
        "http://localhost:8080"
    )


@pytest.mark.parametrize("url", ["ftp://x.test", "not a url", "https://user:pw@x.test"])
def test_settings_invalid_base_url(url):
    with pytest.raises(SodaConfigError) as err:
        load_soda_settings({"SODA_BASE_URL": url})
    assert "pw" not in str(err.value)


def test_settings_token_with_invalid_characters():
    with pytest.raises(SodaConfigError) as err:
        load_soda_settings({"SODA_APP_TOKEN": "bad token"})
    assert "bad token" not in str(err.value)
    assert "invalid characters" in str(err.value)


def _retry_after_case(make_client, status, header, jitter=lambda: 0.0):
    calls = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            headers = {} if header is None else {"Retry-After": header}
            return httpx.Response(status, headers=headers)
        return httpx.Response(200, json=ROWS)

    client, sleeps = make_client(handler, jitter=jitter)
    client.get_page("abcd-1234", {})
    return sleeps


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("3600", [60.0]),
        ("Wed, 21 Oct 2026 07:28:00 GMT", [1.0]),
        ("soon", [1.0]),
        ("-5", [0.0]),
        ("nan", [1.0]),
        ("inf", [1.0]),
        (None, [1.0]),
    ],
)
def test_retry_after_parsing(make_client, header, expected):
    assert _retry_after_case(make_client, 429, header) == expected


def test_503_retry_after_is_respected(make_client):
    assert _retry_after_case(make_client, 503, "30") == [30.0]


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_retryable_5xx(make_client, status):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(status)

    client, sleeps = make_client(handler)
    with pytest.raises(SodaTransientError, match=f"HTTP {status}"):
        client.get_page("abcd-1234", {})
    assert len(calls) == MAX_ATTEMPTS
    assert sleeps == [1.0, 2.0, 4.0]


def test_jitter_is_added_to_backoff(make_client):
    client, sleeps = make_client(lambda r: httpx.Response(503), jitter=lambda: 0.5)
    with pytest.raises(SodaTransientError):
        client.get_page("abcd-1234", {})
    assert sleeps == [1.5, 2.5, 4.5]


def test_wrong_json_shapes_are_permanent(make_client):
    client, _ = make_client(lambda r: httpx.Response(200, json=[]))
    with pytest.raises(SodaPermanentError, match="object"):
        client.get_metadata("abcd-1234")
    client, _ = make_client(lambda r: httpx.Response(200, json=[1, 2]))
    with pytest.raises(SodaPermanentError, match="array"):
        client.get_page("abcd-1234", {})


def test_context_manager_closes():
    with SodaClient(SodaSettings(), transport=httpx.MockTransport(lambda r: None)) as c:
        assert not c._http.is_closed
    assert c._http.is_closed


def test_redirect_is_permanent_and_not_followed(make_client):
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(302, headers={"Location": "https://evil.test/"})

    client, _ = make_client(handler)
    with pytest.raises(SodaPermanentError, match="HTTP 302"):
        client.get_page("abcd-1234", {})
    assert len(calls) == 1


def test_non_transport_request_error_is_permanent(make_client):
    def handler(request):
        raise httpx.DecodingError("bad gzip")

    client, sleeps = make_client(handler)
    with pytest.raises(SodaPermanentError, match="DecodingError"):
        client.get_page("abcd-1234", {})
    assert sleeps == []


def test_uses_app_token_flag_without_exposing_token(make_client):
    with_token, _ = make_client(lambda r: httpx.Response(200, json=[]))
    without_token, _ = make_client(lambda r: httpx.Response(200, json=[]), token=None)
    assert with_token.uses_app_token is True
    assert without_token.uses_app_token is False
    assert TOKEN not in repr(with_token)

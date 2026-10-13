"""Network contract of the SeaweedFS listeners (D119): who can reach what from pits_default.

Run (stack up; reader credentials from the env file):
    uv run --env-file ../pits-app/.env pytest -m contract -q \\
        tests/contract/test_seaweedfs_network_contract.py

Every probe runs curl from a throwaway container of the SAME image/digest as docker-compose.yml,
attached to the compose network `pits_default`, i.e. from the point of view of any other
container on that network. Missing docker or network is a failure, not a skip (D58).

Non-destructive. Reader secrets are forwarded with `docker run -e NAME` (no value), so they never
appear in the host argv; they are expanded by `sh` inside the container. Assertions print only
status codes.

gRPC request (case 5). SeaweedFS serves the internal gRPC services on the S3 port + 10000, so
`seaweedfs:18333`. The call is an HTTP/2 POST (prior knowledge, no TLS/upgrade) to
`/<package>.<Service>/<Method>` with `content-type: application/grpc` and `te: trailers`. The body
is one gRPC length-prefixed message: 1 byte compressed flag + 4 bytes big-endian length, so an
empty protobuf message is the 5 bytes `\\0\\0\\0\\0\\0`. The result is read from the
`grpc-status` header (trailers-only response). Without the key configured, an unauthenticated
RemoveIdentity answers 3 (INVALID_ARGUMENT, "username is required") and changes nothing; once the
listener enforces auth it must answer 16 (UNAUTHENTICATED).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.contract

IMAGE = (  # same pin as docker-compose.yml
    "chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d"
)
NETWORK = os.environ.get("PITS_SWNET_NETWORK", "").strip() or "pits_default"
HOST = os.environ.get("PITS_SWNET_HOST", "").strip() or "seaweedfs"
BUCKET = "pits-raw"
GRPC_PORT = 18333
GRPC_PATH = "/messaging_pb.SeaweedS3IamCache/RemoveIdentity"
READER_ENV = ("PITS_S3_READER_ACCESS_KEY_ID", "PITS_S3_READER_SECRET_ACCESS_KEY")
CURL_CONNECTION_REFUSED = 7


def _docker_run(script: str, env_names: tuple[str, ...] = ()) -> subprocess.CompletedProcess[str]:
    cmd = ["docker", "run", "--rm", "--network", NETWORK, "--entrypoint", "sh"]
    for name in env_names:
        cmd += ["-e", name]  # name only: the value is inherited from our environment
    cmd += [IMAGE, "-c", script]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail("docker run timed out after 120s", pytrace=False)
    if res.returncode != 0:
        pytest.fail(f"docker run failed (exit {res.returncode})", pytrace=False)
    return res


@pytest.fixture(scope="module", autouse=True)
def _docker_and_network() -> None:
    if shutil.which("docker") is None:
        pytest.fail("docker CLI not found: the SeaweedFS network contract needs it", pytrace=False)
    try:
        net = subprocess.run(
            ["docker", "network", "inspect", NETWORK],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except subprocess.TimeoutExpired:
        pytest.fail("docker network inspect timed out after 60s", pytrace=False)
    if net.returncode != 0:
        pytest.fail(
            f"docker network {NETWORK!r} not found or docker daemon down (stack not up?)",
            pytrace=False,
        )


def _reader_env() -> tuple[str, ...]:
    missing = [n for n in READER_ENV if not os.environ.get(n, "").strip()]
    if missing:
        pytest.fail(f"{', '.join(missing)} required (see .env.example)", pytrace=False)
    return READER_ENV


def _region() -> str:
    return os.environ.get("S3_REGION", "").strip() or "us-east-1"


def _http_code(
    script_args: str, env_names: tuple[str, ...] = (), control: bool = False
) -> tuple[int, str]:
    """Run curl and return (curl exit code, HTTP code printed by -w).

    control=True first hits :8333/healthz from the same container, so that a refused port is
    only believed when SeaweedFS itself is alive (positive control).
    """
    script = ""
    if control:
        script += (
            f"echo \"ctl=$(curl -s -m 8 -o /dev/null -w '%{{http_code}}' "
            f'http://{HOST}:8333/healthz)"; '
        )
    script += f"curl -s -m 8 -o /dev/null -w '%{{http_code}}' {script_args}; echo \" rc=$?\""
    out = _docker_run(script, env_names).stdout
    if control:
        ctl = re.search(r"ctl=(\d+)", out)
        if not ctl or ctl.group(1) != "200":
            pytest.fail(
                f"positive control :8333/healthz returned {ctl.group(1) if ctl else 'none'}, "
                "expected 200 (SeaweedFS down?)",
                pytrace=False,
            )
        out = out[ctl.end() :]
    parsed = re.search(r"(\d+) rc=(\d+)\s*$", out)
    if not parsed:
        pytest.fail("unexpected curl output format (no http code / exit code)", pytrace=False)
    return int(parsed.group(2)), parsed.group(1)


@pytest.mark.parametrize("port", [8888, 9333, 8080, 18888, 19333, 18080, 8181, 9101])
def test_internal_ports_refuse_connections(port: int) -> None:
    curl_exit, _ = _http_code(f"http://{HOST}:{port}/", control=True)
    assert curl_exit == CURL_CONNECTION_REFUSED, (
        f"port {port}: curl exit {curl_exit}, expected {CURL_CONNECTION_REFUSED} (refused)"
    )


def test_s3_healthz_is_200() -> None:
    curl_exit, http = _http_code(f"http://{HOST}:8333/healthz")
    assert (curl_exit, http) == (0, "200"), f"healthz: curl exit {curl_exit}, http {http}"


def test_reader_signed_list_is_200() -> None:
    env = _reader_env()
    args = (
        f'--aws-sigv4 "aws:amz:{_region()}:s3" '
        "--variable %PITS_S3_READER_ACCESS_KEY_ID "
        "--variable %PITS_S3_READER_SECRET_ACCESS_KEY "
        "--expand-user '{{PITS_S3_READER_ACCESS_KEY_ID}}:{{PITS_S3_READER_SECRET_ACCESS_KEY}}' "
        f'"http://{HOST}:8333/{BUCKET}?list-type=2&max-keys=1"'
    )
    curl_exit, http = _http_code(args, env)
    assert (curl_exit, http) == (0, "200"), f"signed list: curl exit {curl_exit}, http {http}"


def test_anonymous_list_is_403() -> None:
    curl_exit, http = _http_code(f'"http://{HOST}:8333/{BUCKET}?list-type=2&max-keys=1"')
    assert (curl_exit, http) == (0, "403"), f"anonymous list: curl exit {curl_exit}, http {http}"


@pytest.mark.parametrize("auth", ["none", "fake_bearer"])
def test_grpc_remove_identity_is_unauthenticated(auth: str) -> None:
    header = "-H 'authorization: Bearer not-a-real-token' " if auth == "fake_bearer" else ""
    script = (
        "printf '\\0\\0\\0\\0\\0' > /tmp/frame; "
        "curl -s -m 8 --http2-prior-knowledge -D - -o /dev/null -X POST "
        "-H 'content-type: application/grpc' -H 'te: trailers' "
        f"{header}--data-binary @/tmp/frame http://{HOST}:{GRPC_PORT}{GRPC_PATH}; "
        'echo "curl_exit=$?"'
    )
    res = _docker_run(script)
    status = re.search(r"(?im)^grpc-status:\s*(\d+)", res.stdout)
    curl_exit = re.search(r"curl_exit=(\d+)", res.stdout)
    got = (
        status.group(1) if status else f"none(curl_exit={curl_exit.group(1) if curl_exit else '?'})"
    )
    assert got == "16", f"gRPC RemoveIdentity ({auth}): grpc-status {got}, expected 16"

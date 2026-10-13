"""PitsCliOperator: runs the `pits` CLI as a subprocess (D92).

Why a subprocess and not an import: Airflow and pits live in separate environments on purpose
(D89). The CLI is the contract (argv + exit codes), the same one a human runs.

- argv, never a shell: no quoting or injection surface.
- Environment by allow-list per task (never AIRFLOW__*, never another task's secrets).
- Exit codes: see exit_policy (3 -> retry, anything else non-zero -> fail without retry).
- stdout and stderr (merged, so ordering is kept and a single reader cannot deadlock) go to the
  task log; the values of the secret variables handed to the child are masked there.
- Termination: SIGTERM to the child's process group, SIGKILL after a grace period (the group
  also covers dbt, which `pits transform` runs as its own child). It runs from on_kill AND from
  execute itself on any BaseException: the task runner enforces execution_timeout with SIGALRM
  (AirflowTaskTimeout is raised inside execute) and SIGINT raises KeyboardInterrupt there, and in
  neither case is on_kill guaranteed to find the child. Without it `pits` would be orphaned and
  keep the D90 advisory lock.
- start_new_session=True is kept on purpose: the child gets its own process group, which is the
  only way to signal pits AND dbt together without signalling the task process itself (a plain
  SIGTERM to pits would leave dbt running). The price: if the task process is SIGKILLed with no
  chance to run this code, the child is not in the group the supervisor kills; accepted risk,
  the session lock is released when pits' connection dies.
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from fnmatch import fnmatchcase
from typing import Any

from airflow.sdk import BaseOperator
from airflow.sdk.exceptions import AirflowException, AirflowFailException
from airflow.sdk.log import mask_secret

from pits_cli.exit_policy import Outcome, classify

PITS_BIN = "/opt/pits/.venv/bin/pits"

# Needed by any child process (dbt resolves HOME, python reads locale and temp dir). They carry
# no credentials. PG*/DBT_* are deliberately NOT here: libpq would honor them behind the CLI's back.
BASE_ENV = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR")
# Set on the child, not inherited: its output reaches the task log line by line.
CHILD_ENV = {"PYTHONUNBUFFERED": "1"}

EXTRACT_MODES = ("incremental", "full", "since")
# The supervisor escalates SIGTERM to SIGKILL on the task process after escalation_delay = 5 s
# (airflow.sdk.execution_time.supervisor, 3.3.2): the grace period here must stay well below it,
# or the task process dies mid-wait and the child is left running.
DEFAULT_KILL_TIMEOUT = 3.0


def extract_args(mode: str, since: str | None) -> list[str]:
    """Translate the DAG params into `pits extract trm` flags; ValueError if invalid.

    Validated here too (not only by the params schema of the UI): the REST API and the CLI
    can trigger runs with arbitrary conf.
    """
    if mode not in EXTRACT_MODES:
        raise ValueError(f"extract_mode must be one of {', '.join(EXTRACT_MODES)}; got {mode!r}")
    since = since or None  # the UI sends "" for an empty field
    if mode == "since":
        if since is None:
            raise ValueError("since is required when extract_mode is 'since'")
        try:
            parsed = date.fromisoformat(since)
        except (ValueError, TypeError):
            parsed = None
        if parsed is None or parsed.isoformat() != since:
            raise ValueError("since must be a date in YYYY-MM-DD format")
        return ["--since", since]
    if since is not None:
        raise ValueError("since is only valid when extract_mode is 'since'")
    return ["--full"] if mode == "full" else []


def force_args(force: object) -> list[str]:
    """`--force` when the `force` DAG param is the boolean True; ValueError if it is not a bool.

    Strict on purpose: the REST API and the CLI accept any JSON as conf, and a truthy string such
    as "false" must never turn into --force (which stores a new 50 MB raw batch).
    """
    if not isinstance(force, bool):
        raise ValueError(f"force must be a boolean; got {type(force).__name__}")
    return ["--force"] if force else []


def _trm_extract_args(params: Mapping[str, Any]) -> list[str]:
    return extract_args(params.get("extract_mode", "incremental"), params.get("since"))


def _runt_extract_args(params: Mapping[str, Any]) -> list[str]:
    return force_args(params.get("force", False))


def _divipola_extract_args(params: Mapping[str, Any]) -> list[str]:
    return force_args(params.get("force", False))


# Name -> translator of DAG params into validated argv. A name (not a callable) so the task
# arguments stay serializable and a DAG file cannot smuggle arbitrary code into argv building.
PARAM_ARGS: dict[str, Callable[[Mapping[str, Any]], list[str]]] = {
    "trm_extract": _trm_extract_args,
    "runt_extract": _runt_extract_args,
    "divipola_extract": _divipola_extract_args,
}


def build_env(source: Mapping[str, str], allow: Sequence[str]) -> dict[str, str]:
    """Child environment: variables of `source` matching an allow pattern (fnmatch, case
    sensitive) or BASE_ENV. Anything starting with AIRFLOW is dropped even if a pattern matches."""
    patterns = (*BASE_ENV, *allow)
    return {
        name: value
        for name, value in source.items()
        if not name.upper().startswith("AIRFLOW")
        and any(fnmatchcase(name, pattern) for pattern in patterns)
    }


class PitsCliOperator(BaseOperator):
    """Run `pits <command...>` and translate its exit code (see exit_policy).

    :param command: pits subcommand, e.g. ["extract", "trm"].
    :param env_allow: fnmatch patterns of the environment variables the child may see.
    :param secret_env: exact names whose values are masked in the task log.
    :param param_args: name in PARAM_ARGS; appends the argv derived from the DAG params
        ("trm_extract": extract_mode / since, see extract_args; "runt_extract" and
        "divipola_extract": force, see force_args). Invalid params fail the task before the
        child starts (no retry).
    :param executable: path of the pits script (overridable only by tests).
    :param kill_timeout: seconds between SIGTERM and SIGKILL in on_kill.
    """

    def __init__(
        self,
        *,
        command: Sequence[str],
        env_allow: Sequence[str],
        secret_env: Sequence[str] = (),
        param_args: str | None = None,
        executable: str = PITS_BIN,
        kill_timeout: float = DEFAULT_KILL_TIMEOUT,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.command = list(command)
        self.env_allow = list(env_allow)
        self.secret_env = list(secret_env)
        if param_args is not None and param_args not in PARAM_ARGS:
            raise ValueError(f"param_args must be one of {sorted(PARAM_ARGS)}; got {param_args!r}")
        self.param_args = param_args
        self.executable = executable
        self.kill_timeout = kill_timeout
        self._proc: subprocess.Popen[str] | None = None
        self._lock = (
            threading.RLock()
        )  # on_kill may run in a signal handler of the thread holding it

    def _argv(self, context: Mapping[str, Any]) -> list[str]:
        argv = [self.executable, *self.command]
        if self.param_args is not None:
            params = context.get("params") or {}
            try:
                argv += PARAM_ARGS[self.param_args](params)
            except ValueError as exc:
                raise AirflowFailException(f"invalid DAG params: {exc}") from None
        return argv

    def execute(self, context: Mapping[str, Any]) -> None:
        argv = self._argv(context)
        env = {**build_env(os.environ, self.env_allow), **CHILD_ENV}
        for name in self.secret_env:
            if env.get(name):
                mask_secret(env[name])  # defensive: the CLI must not print them anyway
        self.log.info("running: %s", " ".join(argv))
        try:
            proc = subprocess.Popen(
                argv,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                start_new_session=True,  # own process group: on_kill reaches dbt too
            )
        except OSError as exc:
            raise AirflowFailException(
                f"could not start {self.executable} ({type(exc).__name__})"
            ) from None
        with self._lock:
            self._proc = proc
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                self.log.info("%s", line.rstrip("\n"))
            returncode = proc.wait()
        except BaseException:
            # AirflowTaskTimeout (SIGALRM), KeyboardInterrupt (SIGINT) or any error while reading.
            self._terminate(proc)
            raise
        finally:
            with self._lock:
                self._proc = None
            if proc.stdout is not None:
                proc.stdout.close()

        outcome = classify(returncode)
        if outcome is Outcome.SUCCESS:
            return
        message = f"pits {' '.join(self.command)} exited with code {returncode}"
        if outcome is Outcome.TRANSIENT:
            raise AirflowException(f"{message} (transient, will retry)")
        raise AirflowFailException(f"{message} (permanent, no retry)")

    def on_kill(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is not None:
            self._terminate(proc)

    def _terminate(self, proc: subprocess.Popen[str]) -> None:
        """SIGTERM to the whole group, SIGKILL after kill_timeout; always reaps the child."""
        if proc.poll() is not None:
            return
        self.log.warning("terminating pits (pid %s)", proc.pid)
        self._signal_group(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=self.kill_timeout)
        except subprocess.TimeoutExpired:
            self.log.warning("pits did not exit in %ss; sending SIGKILL", self.kill_timeout)
            self._signal_group(proc, signal.SIGKILL)
            proc.wait()

    @staticmethod
    def _signal_group(proc: subprocess.Popen[str], sig: signal.Signals) -> None:
        try:
            os.killpg(proc.pid, sig)  # pgid == pid (start_new_session)
        except ProcessLookupError:
            pass  # already gone

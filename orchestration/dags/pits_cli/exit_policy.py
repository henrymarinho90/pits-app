"""Exit code policy of the `pits` CLI as seen by Airflow (D92, P4).

The CLI contract (see the docstrings of pits.sources.cli, pits.normalized.cli,
pits.warehouse.load_cli and pits.transform.cli): 0 success, 1 permanent, 2 usage error,
3 transient (safe to retry). Anything else (Popen reports a death by signal as a negative
code, e.g. -9 for the OOM killer's SIGKILL; 126/127 = cannot execute; 137 only appears if a shell
in between translated it) is NOT assumed transient: it fails without retry.
Pure module (no Airflow import) so the policy can be tested and reasoned about on its own.
"""

from __future__ import annotations

from enum import StrEnum

EXIT_OK = 0
EXIT_TRANSIENT = 3


class Outcome(StrEnum):
    SUCCESS = "success"
    TRANSIENT = "transient"
    PERMANENT = "permanent"


def classify(returncode: int) -> Outcome:
    """Map a process return code to an outcome."""
    if returncode == EXIT_OK:
        return Outcome.SUCCESS
    if returncode == EXIT_TRANSIENT:
        return Outcome.TRANSIENT
    return Outcome.PERMANENT

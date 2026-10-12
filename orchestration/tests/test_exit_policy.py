import pytest

from pits_cli.exit_policy import Outcome, classify


def test_zero_is_success():
    assert classify(0) is Outcome.SUCCESS


def test_three_is_transient():
    assert classify(3) is Outcome.TRANSIENT


@pytest.mark.parametrize("code", [1, 2, 4, 126, 127, 137, 139, 255, -1, -9, -15])
def test_everything_else_is_permanent(code):
    """Usage errors, signals (negative), OOM kill (137) and unknown codes never retry (P4)."""
    assert classify(code) is Outcome.PERMANENT

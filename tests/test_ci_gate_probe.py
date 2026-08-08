"""Temporary: proves CI fails the run (and so blocks deploy) on a red test."""


def test_deliberately_failing_probe() -> None:
    assert 1 == 2, "intentional failure to verify the CI gate"

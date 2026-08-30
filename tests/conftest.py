from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def disable_invocation_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test suite out of the user's real WorkBundle usage database."""
    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "0")

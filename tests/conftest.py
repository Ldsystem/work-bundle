from __future__ import annotations

import pytest
import sys


@pytest.fixture(autouse=True)
def disable_invocation_observation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the test suite out of the user's real WorkBundle usage database."""
    monkeypatch.setenv("WORK_BUNDLE_INVOCATION_LOG", "0")


@pytest.fixture(autouse=True)
def isolated_reviewer_receipt_store(tmp_path, monkeypatch):
    """Exercise native receipt lookup without using the user's runtime store."""
    module = sys.modules.get("review_runtime")
    if module is not None:
        monkeypatch.setattr(module, "reviewer_runtime_root", lambda root: tmp_path.parent / f"reviewer-runtime-{tmp_path.name}")

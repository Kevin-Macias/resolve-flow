"""Existing offline scenarios explicitly use the legacy demo identity fixture."""

import pytest


@pytest.fixture(autouse=True)
def demo_auth_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "demo")

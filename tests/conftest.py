"""Keep tests away from the developer's live agent homes."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_agent_home(tmp_path, monkeypatch):
    home = tmp_path / "isolated-home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for key in ("CODEX_HOME", "CLAUDE_CONFIG_DIR", "AI_CONFIG_HOME"):
        monkeypatch.delenv(key, raising=False)

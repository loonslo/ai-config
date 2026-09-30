"""Sandbox homes that replicate real agent layouts, with placeholder content.

The directory shapes mirror what the agents create on a real machine: rules
entries, persona and memory files, skills, settings, and credential/runtime
material.  Every credential or runtime decoy carries ``SENTINEL`` so a test can
prove its content never appears in any output, and ``ReadTracker`` records which
files were opened so a test can prove protected files were never read.

Nothing here touches the real home directory: every path is below ``tmp_path``.
"""
from __future__ import annotations

import builtins
import io
from pathlib import Path
from typing import Any, Iterable

SENTINEL = "SENTINEL-DO-NOT-READ-7f3k"

RULE_TOPICS = ("instructions", "principles", "engineering", "python", "langgraph", "rag", "security")

#: Lines a user typically copies into every agent before adopting ai-config.
HAND_WRITTEN_RULES = (
    "# Developer Profile\n"
    "\n"
    "## Coding Style\n"
    "\n"
    "- 默认使用 Python 3.14。\n"
    "- 测试默认使用 pytest。\n"
)


def write_store(root: Path, *, instructions: str | None = None) -> Path:
    """A configuration store with the standard layout (``common/`` + templates)."""
    for name in RULE_TOPICS:
        path = root / "common" / f"{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n\n- shared {name} rule\n", encoding="utf-8")
    if instructions is not None:
        (root / "common" / "instructions.md").write_text(instructions, encoding="utf-8")
    (root / "codex").mkdir(parents=True, exist_ok=True)
    (root / "claude").mkdir(parents=True, exist_ok=True)
    (root / "codex" / "config.toml").write_text('model_reasoning_effort = "high"\nweb_search = "cached"\n', encoding="utf-8")
    (root / "claude" / "settings.shared.json").write_text('{"autoMemoryEnabled": true}\n', encoding="utf-8")
    return root


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def _secret(path: Path) -> Path:
    return _write(path, f"{SENTINEL}\n")


def build_home(home: Path, *, agents: Iterable[str] = ("codex", "claude", "codebuddy", "workbuddy", "workbuddy-ai", "cc-switch", "doubao")) -> dict[str, list[Path]]:
    """Create agent roots below ``home`` and return the protected decoy files."""
    wanted = set(agents)
    protected: list[Path] = []
    if "codex" in wanted:
        root = home / ".codex"
        _write(root / "AGENTS.md", HAND_WRITTEN_RULES)
        _write(root / "config.toml", 'model = "example"\n')
        protected += [_secret(root / "auth.json"), _secret(root / "secrets" / "token.bin"), _secret(root / "sessions" / "s.jsonl")]
        _write(root / "skills" / "diary" / "SKILL.md", "---\nname: diary\n---\nwrite a diary\n")
        _write(root / "skills" / ".system" / "builtin" / "SKILL.md", "---\nname: builtin\n---\n")
        (root / "memories").mkdir(parents=True, exist_ok=True)
    if "claude" in wanted:
        root = home / ".claude"
        _write(root / "CLAUDE.md", HAND_WRITTEN_RULES)
        protected += [
            _write(root / "settings.json", '{"env": {"ANTHROPIC_AUTH_TOKEN": "%s"}, "model": "x"}\n' % SENTINEL),
            _secret(root / ".credentials.json"),
            _secret(root / "history.jsonl"),
        ]
        _write(root / "skills" / "review" / "SKILL.md", "---\nname: review\n---\nreview code\n")
        _write(root / "projects" / "demo" / "memory" / "MEMORY.md", "# memory\n")
    if "codebuddy" in wanted:
        root = home / ".codebuddy"
        protected += [
            _write(root / "settings.json", '{"enabledPlugins": {}, "note": "%s"}\n' % SENTINEL),
            _secret(root / "models.json"),
            _secret(root / "connectors" / "default" / "mcp.json"),
        ]
        _write(root / "memery" / "abc_memery.md", "remembered\n")
        _write(root / "skills" / "review" / "SKILL.md", "---\nname: review\n---\nreview code\n")
    for instance in ("workbuddy", "workbuddy-ai"):
        if instance not in wanted:
            continue
        root = home / f".{instance}"
        for name in ("SOUL.md", "USER.md", "IDENTITY.md"):
            _write(root / name, f"# {name}\npersona text\n")
        _write(root / "MEMORY.md", "# MEMORY.md\nlong-term memory\n")
        _write(root / "memory" / "2026-09-01.md", "daily note\n")
        protected += [
            _secret(root / "keyblob"),
            _secret(root / "security" / "vault.bin"),
            _secret(root / "app" / "connector-keys" / "k.json"),
            _secret(root / "workbuddy.db"),
            _write(root / "settings.json", '{"claw": {"users": "%s"}}\n' % SENTINEL),
        ]
        _write(root / "skills" / "office" / "SKILL.md", "---\nname: office\n---\noffice work\n")
    if "cc-switch" in wanted:
        root = home / ".cc-switch"
        protected += [_secret(root / "settings.json"), _secret(root / "cc-switch.db")]
        _write(root / "skills" / "review" / "SKILL.md", "---\nname: review\n---\na different review skill\n")
    if "agents-skills" in wanted:
        _write(home / ".agents" / "skills" / "diary" / "SKILL.md", "---\nname: diary\n---\nwrite a diary\n")
    if "doubao" in wanted:
        protected.append(_secret(home / "AppData" / "Roaming" / "Doubao" / "public_config.json"))
    if "trae-cn-dir" in wanted:
        _write(home / ".trae-cn" / "user_rules" / "AGENTS.md", HAND_WRITTEN_RULES)
    if "trae-file" in wanted:
        _write(home / ".trae" / "user_rules.md", HAND_WRITTEN_RULES)
    return {"protected": protected}


def device_raw(tmp_path: Path, store: Path, *, legacy: dict[str, Path] | None = None, agents: dict[str, Any] | None = None) -> dict[str, Any]:
    """A device configuration pointing at ``store`` with the given agents."""
    raw: dict[str, Any] = {
        "device": "windows-a",
        "state_dir": str(tmp_path / "state"),
        "memory_repo": str(tmp_path / "memory"),
        "config_repo": str(store),
        "codex_keys": [],
        "codex_overrides": {},
        "claude_keys": [],
        "claude_overrides": {},
        "tool_versions": {},
        "additional_sources": [],
        "memories": [],
        "projects": {},
    }
    for name, root in (legacy or {}).items():
        raw[name] = str(root)
    if agents:
        raw["agents"] = {key: {**value, "root": str(value["root"])} for key, value in agents.items()}
    return raw


class ReadTracker:
    """Record every file opened for reading, so a test can assert what was read."""

    def __init__(self, monkeypatch: Any) -> None:
        self.opened: list[Path] = []
        original_open = builtins.open
        original_read_bytes = Path.read_bytes
        original_read_text = Path.read_text
        tracker = self

        def tracking_open(file: Any, mode: str = "r", *args: Any, **kwargs: Any) -> Any:
            if isinstance(file, (str, Path)) and "r" in mode and "+" not in mode:
                tracker.opened.append(Path(file))
            return original_open(file, mode, *args, **kwargs)

        def tracking_read_bytes(self: Path) -> bytes:
            tracker.opened.append(Path(self))
            return original_read_bytes(self)

        def tracking_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
            tracker.opened.append(Path(self))
            return original_read_text(self, *args, **kwargs)

        monkeypatch.setattr(builtins, "open", tracking_open)
        monkeypatch.setattr(io, "open", tracking_open)
        monkeypatch.setattr(Path, "read_bytes", tracking_read_bytes)
        monkeypatch.setattr(Path, "read_text", tracking_read_text)

    def touched(self, paths: Iterable[Path]) -> list[Path]:
        wanted = {Path(path).resolve() for path in paths}
        return sorted({path.resolve() for path in self.opened if path.resolve() in wanted})

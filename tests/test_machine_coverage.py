from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from _agent_homes import ReadTracker
from _machine_fixtures import build_machine_home
from sync_core.machine.backup import prepare_backup
from sync_core.machine.catalog import Decision
from sync_core.machine.config import load_config
from sync_core.machine.coverage import Ledger, Limits, SourceRoot, walk_root


def test_ledger_uniqueness_and_report_accounting():
    ledger = Ledger()
    ledger.seen("codex_home", "AGENTS.md", 20, Decision("CX-01", "A", "carry"))
    ledger.carried("codex_home", "AGENTS.md", Decision("CX-01", "A", "carry"))
    ledger.seen("codex_home", "unknown", 5, Decision(None, "U", "unclassified"))
    ledger.pruned("codex_home", "plugins", "CX-16", 3)
    with pytest.raises(ValueError, match="duplicate"):
        ledger.seen("codex_home", "unknown", 5, Decision(None, "U", "unclassified"))
    totals = ledger.report()["totals"]
    assert totals["files"] + totals["pruned_entries"] == 5
    assert totals["carried"] == 1


def test_walk_never_reads_credentials_unknown_or_history(tmp_path, monkeypatch):
    root = tmp_path / "codex"
    root.mkdir()
    for name in ("auth.json", "history.jsonl", "unknown.txt", "AGENTS.md"):
        (root / name).write_text("content", encoding="utf-8")
    (root / "plugins" / "cache" / "deep").mkdir(parents=True)
    (root / "plugins" / "cache" / "deep" / "secret.txt").write_text("content", encoding="utf-8")
    tracker = ReadTracker(monkeypatch)
    ledger = Ledger()
    source = SourceRoot("codex_home", "codex", "main", lambda h, e: root)
    candidates = list(walk_root(source, home=tmp_path, environ={}, excluded=lambda p: False,
                                ledger=ledger, limits=Limits()))
    assert tracker.opened == []
    assert [c.relative for c in candidates] == ["AGENTS.md"]
    report = ledger.report()
    assert report["totals"]["files"] == 4
    assert report["roots"][0]["pruned"] == [{"path": "plugins", "rule_id": "CX-16", "entries": 1}]
    assert report["roots"][0]["unclassified"]["samples"] == ["unknown.txt"]


def test_observer_keeps_selected_file_bytes_and_fields_unchanged(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    out = tmp_path / "out"
    out.mkdir()
    config_file = tmp_path / "machine.json"
    config_file.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    config = load_config(config_file, home=paths["home"])
    (paths["home"] / ".codex" / "new-file.txt").write_text("new", encoding="utf-8")
    params = dict(home=paths["home"], config=config, out=out, environ={}, os_name="windows",
                  now=datetime(2026, 10, 9, tzinfo=timezone.utc), software={"versions": {}, "unverified": []}, git_keys=[])
    old = prepare_backup(**params, observe_coverage=False)
    new = prepare_backup(**params)
    old_entries = [e for e in old.writer.entries if e["kind"] != "report"]
    new_entries = [e for e in new.writer.entries if e["kind"] != "report"]
    assert old_entries == new_entries
    for e in old_entries:
        assert old.writer._files[e["archive_path"]] == new.writer._files[e["archive_path"]]
    for path, data in old.writer._files.items():
        if path != "reports/summary.md":
            assert new.writer._files[path] == data
    report = json.loads(new.writer._files["reports/coverage.json"])
    assert "new-file.txt" in next(r for r in report["roots"] if r["id"] == "codex_home")["unclassified"]["samples"]
    assert "未定性文件" in new.writer._files["reports/summary.md"].decode()
    assert any(f["source"] == "claude_json/.claude.json" for f in report["fields"])
    assert list(out.iterdir()) == []


def test_unknown_samples_capped_and_scan_limits_honest(tmp_path):
    for n in range(25):
        (tmp_path / f"unknown{n}.txt").write_text("x", encoding="utf-8")
    source = SourceRoot("codex_home", "codex", "main", lambda h, e: tmp_path)
    ledger = Ledger()
    list(walk_root(source, home=tmp_path, environ={}, excluded=lambda p: False, ledger=ledger, limits=Limits()))
    assert ledger.report()["totals"]["unclassified"] == 25
    assert len(ledger.report()["roots"][0]["unclassified"]["samples"]) == 20
    limited = Ledger()
    list(walk_root(source, home=tmp_path, environ={}, excluded=lambda p: False, ledger=limited, limits=Limits(max_entries=2)))
    assert not limited.report()["totals"]["complete"]


def test_project_source_tree_is_outside_scan_boundary(tmp_path, monkeypatch):
    (tmp_path / "src" / "deep").mkdir(parents=True)
    (tmp_path / "src" / "deep" / "app.py").write_text("code", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "note.md").write_text("note", encoding="utf-8")
    source = SourceRoot("project:p1", "claude", "main", lambda h, e: tmp_path)
    ledger = Ledger()
    tracker = ReadTracker(monkeypatch)
    list(walk_root(source, home=tmp_path, environ={}, excluded=lambda p: False, ledger=ledger, limits=Limits()))
    assert tracker.opened == []
    assert ("project:p1", "src/deep/app.py") not in ledger._seen
    assert {"path": "src", "rule_id": "PJ-07", "entries": 0} in ledger.report()["roots"][0]["pruned"]


def test_link_root_is_not_followed(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symbolic-link privilege unavailable")
    ledger = Ledger()
    list(walk_root(SourceRoot("codex_home", "codex", "main", lambda h, e: link), home=tmp_path,
                   environ={}, excluded=lambda p: False, ledger=ledger, limits=Limits()))
    assert ledger.report()["totals"]["files"] == 0
    assert not ledger.report()["totals"]["complete"]


def test_sensitive_names_and_values_are_not_echoed(tmp_path):
    from sync_core.machine.coverage import observe_fields
    ledger = Ledger()
    email = "person" + "@" + "example.org"
    ledger.seen("codex_home", email + ".txt", 1, Decision(None, "U", "unclassified"))
    observe_fields({"env": {"API_TOKEN": "sensitive-value"}, "projects": {str(tmp_path): {"unknown": "sensitive-value"}}},
                   root="claude_home", source="settings.json", ledger=ledger)
    report = json.dumps(ledger.report(), ensure_ascii=False)
    assert email not in report
    assert "sensitive-value" not in report
    assert str(tmp_path) not in report


def test_carried_is_unique_and_uses_observed_nature():
    ledger = Ledger()
    decision = Decision('CX-01', 'A', 'carry')
    ledger.seen('codex_home', 'AGENTS.md', 5, decision)
    ledger.carried('codex_home', 'AGENTS.md', Decision('SK-02', 'C', 'carry'))
    ledger.carried('codex_home', 'AGENTS.md', decision)
    assert ledger.report()['totals']['carried'] == 1
    assert ledger.report()['roots'][0]['by_nature']['A']['carried'] == 1


@pytest.mark.parametrize('selected', [False, True])
def test_history_coverage_tracks_accepted_sources_not_segments(tmp_path, monkeypatch, selected):
    home = tmp_path/'home'; root = home/'.codex'; folder = root/'sessions/2026'
    folder.mkdir(parents=True)
    good = folder/'good.jsonl'; good.write_bytes(b'{"message":"hello"}\n'*5)
    raw = folder/'content.bin'; raw.write_bytes(b'\xffopaque\n')
    bad = folder/'bad.jsonl'; bad.write_bytes(b'{broken}\n')
    protected = root/'auth.json'; protected.write_bytes(b'protected sentinel')
    out = tmp_path/'out'; out.mkdir()
    from sync_core.machine import backup as module
    # A streaming history source remains countable above the main-file threshold.
    monkeypatch.setattr(module, 'Limits', lambda: Limits(max_file_bytes=1))
    tracker = ReadTracker(monkeypatch)
    plan = prepare_backup(home=home, config=load_config(tmp_path/'none.json', home=home), out=out,
                          agents=frozenset({'codex'}), environ={}, software={'versions':{}}, git_keys=[],
                          groups=frozenset({'history'} if selected else {'rules'}))
    covered = next(r for r in plan.coverage['roots'] if r['id'] == 'codex_home')
    assert covered['by_nature']['H']['files'] == 3
    assert covered['by_nature']['H']['carried'] == (2 if selected else 0)
    assert not tracker.touched([protected])
    if not selected:
        assert not tracker.touched([good, raw, bad])

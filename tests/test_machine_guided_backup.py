from datetime import datetime, timezone
import json

from _agent_homes import ReadTracker, SENTINEL
from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.backup import apply_backup, prepare_backup
from sync_core.machine.bundle import read_bundle
from sync_core.machine.config import load_config
from sync_core.machine.guide_backup import filter_folders, guide_backup
from sync_core.machine.guided import GuideIO, clean_dragged_path, desktop_path, forbidden_words


NOW = datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
SOFTWARE = {"versions": {"python": "3.14.0"}, "unverified": []}


def _setup(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    source = tmp_path / "config.json"
    source.write_text(json.dumps({"core_projects": [str(paths["project"])]}), encoding="utf-8")
    output = tmp_path / "desktop"
    output.mkdir()
    return paths, load_config(source, home=paths["home"]), output


def _io(answers):
    iterator = iter(answers)
    screen = []
    return GuideIO(read=lambda prompt: next(iterator), write=screen.append), screen


def test_all_enter_guide_matches_expert_bundle_and_keeps_sources(tmp_path):
    paths, config, desktop = _setup(tmp_path)
    before = snapshot_tree(paths["home"])
    ui, screen = _io([""] * 5)
    assert guide_backup(io=ui, home=paths["home"], config=config, config_used=True, environ={},
                        os_name="windows", clock=lambda: NOW, desktop=lambda home: desktop,
                        software=SOFTWARE, git_keys=[]) == 0
    bundle = next(desktop.glob("*.zip"))
    assert_no_sentinel(bundle)
    manifest, _ = read_bundle(bundle)
    other = tmp_path / "expert-output"
    other.mkdir()
    plan = prepare_backup(home=paths["home"], config=config, out=other, name="AI备份", environ={},
                          os_name="windows", now=NOW, software=SOFTWARE, git_keys=[])
    assert apply_backup(plan)["content_id"] == manifest["content_id"]
    assert_tree_unchanged(before, paths["home"])
    assert forbidden_words("\n".join(ui.authored)) == []
    assert any("个人记忆" in line for line in screen)


def test_quit_zero_writes_and_missing_config_still_works(tmp_path):
    paths, config, desktop = _setup(tmp_path)
    before = snapshot_tree(paths["home"])
    ui, _ = _io(["q", ""])
    assert guide_backup(io=ui, home=paths["home"], environ={}, desktop=lambda home: desktop) == 0
    assert list(desktop.iterdir()) == []
    assert_tree_unchanged(before, paths["home"])
    ui, _ = _io([""] * 5)
    assert guide_backup(io=ui, home=paths["home"], environ={}, os_name="windows", clock=lambda: NOW,
                        desktop=lambda home: desktop, discover=lambda **kwargs: [str(paths["project"])],
                        software=SOFTWARE, git_keys=[]) == 0
    assert len(list(desktop.glob("*.zip"))) == 1
    assert not (paths["home"] / ".ai-sync" / "machine.config.json").exists()


def test_deselected_assistant_has_no_entries_or_reads(tmp_path, monkeypatch):
    paths, config, desktop = _setup(tmp_path)
    tracker = ReadTracker(monkeypatch)
    ui, _ = _io(["", "4", "", "", "", ""])
    assert guide_backup(io=ui, home=paths["home"], config=config, config_used=True, environ={},
                        os_name="windows", clock=lambda: NOW, desktop=lambda home: desktop,
                        software=SOFTWARE, git_keys=[]) == 0
    manifest, _ = read_bundle(next(desktop.glob("*.zip")))
    assert all(entry["agent"] != "workbuddy-ai" for entry in manifest["entries"])
    assert tracker.touched([paths["home"] / ".workbuddy-ai" / "settings.json",
                            paths["home"] / ".workbuddy-ai" / "SOUL.md"]) == []


def test_quit_at_final_confirmation_keeps_everything_unchanged(tmp_path):
    paths, config, desktop = _setup(tmp_path)
    before = snapshot_tree(paths["home"])
    ui, _ = _io(["", "", "", "q", ""])
    assert guide_backup(io=ui, home=paths["home"], config=config, config_used=True, environ={},
                        os_name="windows", desktop=lambda home: desktop,
                        software=SOFTWARE, git_keys=[]) == 0
    assert list(desktop.iterdir()) == []
    assert_tree_unchanged(before, paths["home"])


def test_unsafe_desktop_falls_back_outside_assistant_root(tmp_path):
    paths, config, _ = _setup(tmp_path)
    ui, screen = _io([""] * 5)
    assert guide_backup(io=ui, home=paths["home"], config=config, config_used=True, environ={},
                        os_name="windows", clock=lambda: NOW,
                        desktop=lambda home: home / ".codex",
                        software=SOFTWARE, git_keys=[]) == 0
    assert len(list(paths["home"].glob("AI备份-*.zip"))) == 1
    assert list((paths["home"] / ".codex").glob("*.zip")) == []
    assert any("桌面位置不适合" in line for line in screen)


def test_desktop_fallback_and_dragged_paths(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    assert desktop_path(home, known_folder=lambda: None) == home
    desktop = home / "Desktop"
    desktop.mkdir()
    assert desktop_path(home, known_folder=lambda: None) == desktop
    redirected = tmp_path / "redirected"
    redirected.mkdir()
    assert desktop_path(home, known_folder=lambda: redirected) == redirected
    path = tmp_path / "folder with spaces"
    assert clean_dragged_path('"' + str(path) + '"') == path
    assert clean_dragged_path(str(path).replace(" ", "\\ ")) == path
    scratch = home / "scratch-workspaces" / "demo"
    scratch.mkdir(parents=True)
    project = home / "project"
    project.mkdir()
    assert filter_folders([str(home), str(scratch), str(project), str(project), str(home / "missing")],
                          home=home, patterns=("**/scratch-workspaces/**",), os_name="windows") == (project,)


def test_unexpected_failure_never_discloses_exception_values(tmp_path):
    paths, config, desktop = _setup(tmp_path)
    ui, screen = _io(["", "", "", ""])
    def fail(home):
        raise RuntimeError(SENTINEL)
    assert guide_backup(io=ui, home=paths["home"], config=config, config_used=True, environ={},
                        desktop=fail, software=SOFTWARE, git_keys=[]) == 1
    assert SENTINEL not in "\n".join(screen)
    log = next((paths["home"] / ".ai-sync" / "state").glob("machine-guide-*.log"))
    assert SENTINEL not in log.read_text(encoding="utf-8")
    assert ui.authored[-1] == "错误码：E7404"
    assert list(desktop.iterdir()) == []

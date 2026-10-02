from pathlib import Path
import subprocess

from sync_core.machine.paths import RootMap, derive_project_dir, git_root, norm, real_case, same_path


def test_windows_spelling_and_case():
    assert norm(r"\\?\D:\\X/ai-config\\", "windows") == "d:/X/ai-config"
    assert same_path("D:\\X\\ai-config\\", "d:/x/AI-CONFIG", "windows")
    assert not same_path("/X/project", "/x/project", "mac")
    assert norm("D:\\\\", "windows") == "d:/"


def test_project_dir_uses_original_native_spelling():
    assert derive_project_dir(r"D:\x\ai-config") == "D--x-ai-config"
    assert derive_project_dir(r"d:\x\ai-config") == "d--x-ai-config"
    assert derive_project_dir("x" * 201) is None


def test_root_map_longest_match_and_orphan():
    mapping = RootMap(((r"D:\work", "/Users/me/work"), (r"D:\work\nested", "/other")), "windows", "mac")
    assert mapping.map(r"d:\WORK\nested\Project") == "/other/Project"
    assert mapping.map(r"D:\work\Project") == "/Users/me/work/Project"
    assert mapping.map(r"D:\workspace2\Project") is None
    assert RootMap().map(r"D:\work\Project") == "d:/work/Project"


def test_git_root_primary_checkout_and_plain_folder(tmp_path, monkeypatch):
    repo = tmp_path / "main"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=x@example.invalid", "-c", "user.name=X", "commit", "--allow-empty", "-qm", "init"], check=True)
    nested = repo / "nested"
    nested.mkdir()
    assert git_root(nested) == repo.resolve()
    worktree = tmp_path / "other"
    subprocess.run(["git", "-C", str(repo), "worktree", "add", "-q", "-b", "test-worktree", str(worktree)], check=True)
    assert git_root(worktree) == repo.resolve()
    plain = tmp_path / "plain"
    plain.mkdir()
    def no_git(*args, **kwargs):
        raise subprocess.CalledProcessError(128, "git")
    monkeypatch.setattr(subprocess, "run", no_git)
    assert git_root(plain) == plain.resolve()


def test_real_case_preserves_existing_names(tmp_path):
    folder = tmp_path / "MixedCase"
    folder.mkdir()
    assert real_case(folder / "new.txt") == folder / "new.txt"

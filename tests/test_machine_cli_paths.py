from _machine_fixtures import build_machine_home
from scripts.machine import check_claude_project_dirs


def test_path_self_check_reads_only_project_keys(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    report = check_claude_project_dirs(home=paths["home"], claude_root=paths["home"] / ".claude")
    assert report["project_keys"] >= 1
    assert report["matching_dirs"] == 1
    assert report["observed_transcript_dirs"] == 1

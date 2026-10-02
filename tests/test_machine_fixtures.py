from _machine_fixtures import assert_no_sentinel, assert_tree_unchanged, build_machine_home, snapshot_tree
from sync_core.machine.bundle import BundleWriter


def test_synthetic_home_and_sentinel_assertion(tmp_path):
    paths = build_machine_home(tmp_path / "home")
    before = snapshot_tree(paths["home"])
    assert_tree_unchanged(before, paths["home"])
    writer = BundleWriter(tmp_path / "safe.zip")
    writer.add_report("summary.md", "safe")
    writer.finalize()
    assert_no_sentinel(tmp_path / "safe.zip")

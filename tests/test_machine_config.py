import json

import pytest

from sync_core.machine.config import load_config


def test_missing_config_needs_no_file_and_uses_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_CONFIG_HOME", str(tmp_path / "data"))
    config = load_config(home=tmp_path)
    assert config.core_projects == ()
    assert config.include_desktop_fields == frozenset()
    assert config.instances["workbuddy"] == tmp_path / ".workbuddy"
    assert not (tmp_path / "data").exists()


def test_config_rejects_unknown_and_device_specific_fields(tmp_path):
    path = tmp_path / "machine.config.json"
    for value in ({"unexpected": True}, {"include_desktop_fields": ["microphoneInputDeviceId"]},
                  {"core_projects": ["relative/project"]}, {"root_map": [{"from": "relative", "to": "/target"}]}):
        path.write_text(json.dumps(value), encoding="utf-8")
        with pytest.raises(ValueError):
            load_config(path, home=tmp_path)


def test_config_accepts_windows_to_mac_root_map(tmp_path):
    path = tmp_path / "machine.config.json"
    path.write_text(json.dumps({"root_map": [{"from": "D:/Workspace", "to": "/Users/demo/Workspace"}]}), encoding="utf-8")
    config = load_config(path, home=tmp_path, source_os="windows", target_os="mac")
    assert config.root_map.map(r"D:\Workspace\ai-config") == "/Users/demo/Workspace/ai-config"

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def test_config_sync_import_does_not_load_cli_module() -> None:
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from sync_core import config_sync; import sys; "
            "assert 'scripts.sync' not in sys.modules",
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_application_service_import_and_construction_are_side_effect_free(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    local = tmp_path / "data" / "device.json"
    script = (
        "from pathlib import Path; import sys; "
        "from sync_core.application import ApplicationService; "
        f"service = ApplicationService(Path({str(local)!r})); "
        "assert not Path(service.local_path).exists(); "
        "assert 'scripts.sync' not in sys.modules"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert not local.exists()

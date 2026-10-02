"""JSON-lines sidecar entry point for the desktop client."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = (
    Path(getattr(sys, "_MEIPASS"))
    if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
    else Path(__file__).resolve().parents[1]
)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sync_core.application.protocol import ApplicationProtocol
from sync_core.layout import default_device_config_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local", type=Path, default=None, help="device configuration path")
    parser.add_argument("--template-root", type=Path, default=ROOT, help="read-only bundled template directory")
    args = parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if not stream.isatty():
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (AttributeError, OSError, ValueError):
                pass
    ApplicationProtocol(
        args.local or default_device_config_path(),
        template_root=args.template_root,
    ).serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()

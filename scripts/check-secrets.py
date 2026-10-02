"""Scan tracked and unignored files, including examples; never print matches."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
from sync_core.utils import SECRET

names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).decode().split("\0")
findings = []
for name in set(filter(None, names)):
    path = root / name
    if path.is_file():
        content = path.read_text(encoding="utf-8", errors="replace")
        if SECRET.search(content):
            findings.append(name)
for name in sorted(findings):
    print(f"Potential secret: {name}")
print(f"Secret scan: {len(findings)} findings")
raise SystemExit(bool(findings))

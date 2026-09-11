"""Scan tracked and unignored files, including examples; never print matches."""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
patterns = [re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
            re.compile(r"(?im:^[A-Z0-9_]*(?:PASSWORD|PASSWD|TOKEN|API_KEY)\s*=\s*\S+)"),
            re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[\"'][^\"']{12,}[\"']")]
names = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"]).decode().split("\0")
findings = []
for name in set(filter(None, names)):
    path = root / name
    if path.is_file():
        content = path.read_text(encoding="utf-8", errors="replace")
        if any(pattern.search(content) for pattern in patterns):
            findings.append(name)
for name in sorted(findings):
    print(f"Potential secret: {name}")
print(f"Secret scan: {len(findings)} findings")
raise SystemExit(bool(findings))

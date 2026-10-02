"""Collect installed dependency notices, reporting gaps instead of hiding them."""
from __future__ import annotations
import argparse
from importlib import metadata
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

NOTICE_PREFIXES = ("LICENSE", "LICENCE", "NOTICE", "COPYING")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fetch-missing", action="store_true", help="Fetch missing Cargo notices from the exact published Git commit on GitHub")
    args = parser.parse_args()
    output = args.output.absolute()
    if output.exists():
        raise SystemExit("Use a new notice directory; no overwrite")
    output.mkdir(parents=True)
    root = Path(__file__).resolve().parents[1]
    records = []
    excluded_optional = []
    def github_notices(package):
        directory = Path(package["manifest_path"]).parent
        vcs = directory / ".cargo_vcs_info.json"
        repository = urlsplit(package.get("repository") or "")
        if not vcs.is_file() or repository.netloc != "github.com":
            return [], None
        commit = json.loads(vcs.read_text())["git"]["sha1"]
        slug = repository.path.strip("/").removesuffix(".git")
        if len(slug.split("/")) != 2 or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
            return [], None
        def read(url):
            with urlopen(Request(url, headers={"User-Agent": "ai-config-notice-collector"}), timeout=15) as response:
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError("Upstream license response exceeds bound")
                return data
        listing = json.loads(read(f"https://api.github.com/repos/{slug}/contents?ref={commit}"))
        staging = output / "upstream" / (package["name"] + "-" + package["version"])
        files, sources = [], []
        for item in listing:
            if item["type"] != "file" or not item["name"].upper().startswith(NOTICE_PREFIXES):
                continue
            url = f"https://raw.githubusercontent.com/{slug}/{commit}/{quote(item['name'])}"
            data = read(url)
            staging.mkdir(parents=True, exist_ok=True)
            target = staging / item["name"]
            target.write_bytes(data)
            files.append(target)
            sources.append(url)
        if not files and package.get("license") == "MPL-2.0":
            url = "https://www.mozilla.org/MPL/2.0/"
            data = read(url)
            staging.mkdir(parents=True, exist_ok=True)
            target = staging / "LICENSE-MPL-2.0.html"
            target.write_bytes(data)
            files.append(target)
            sources.append(url)
        return files, {"commit": commit, "sources": sources}
    def collect(kind, name, version, license_name, candidates):
        files = []
        destination = output / kind / (name.replace("/", "_") + "-" + version)
        for index, source in enumerate(candidates):
            if source.is_file() and not source.is_symlink():
                destination.mkdir(parents=True, exist_ok=True)
                target = destination / f"{index}-{source.name}"
                shutil.copy2(source, target)
                files.append(target.relative_to(output).as_posix())
        records.append({"ecosystem": kind, "name": name, "version": version, "license": license_name, "files": files, "notice_missing": not files})
    runtime_license = Path(sys.base_prefix) / "LICENSE.txt"
    collect("runtime", "Python", sys.version.split()[0], "PSF", [runtime_license])
    for line in (root / "desktop/requirements-windows.lock.txt").read_text().splitlines():
        if "==" not in line:
            continue
        name, version = line.split("==")
        dist = metadata.distribution(name)
        candidates = [Path(dist.locate_file(item)) for item in dist.files or [] if any(word in str(item).upper() for word in NOTICE_PREFIXES)]
        collect("python", name, version, dist.metadata.get("License-Expression", dist.metadata.get("License", "unknown")), candidates)
    lock = json.loads((root / "desktop/package-lock.json").read_text())
    for relative, specification in lock["packages"].items():
        if not relative or "node_modules" not in relative:
            continue
        package = root / "desktop" / relative
        if not package.is_dir() and specification.get("optional"):
            excluded_optional.append({"name": relative, "version": specification["version"], "reason": "not installed on this platform"})
            continue
        candidates = [path for path in package.glob("*") if path.name.upper().startswith(NOTICE_PREFIXES)]
        name = relative.split("node_modules/")[-1]
        parent_name = "oxlint" if name.startswith("@oxlint/binding-") else "rolldown" if name.startswith("@rolldown/binding-") else "@tauri-apps/cli" if name.startswith("@tauri-apps/cli-") else None
        inherited = None
        if not any(path.is_file() for path in candidates) and parent_name:
            parent = root / "desktop/node_modules" / parent_name
            info = json.loads((parent / "package.json").read_text())
            if info["version"] == specification["version"]:
                candidates = [path for path in parent.glob("*") if path.name.upper().startswith(NOTICE_PREFIXES)]
                inherited = parent_name + "@" + info["version"]
        collect("npm", name, specification["version"], specification.get("license", "unknown"), candidates)
        if inherited:
            records[-1]["license_source_package"] = inherited
    cargo = json.loads(subprocess.check_output(["cargo", "metadata", "--format-version", "1", "--locked", "--offline", "--filter-platform", "x86_64-pc-windows-msvc"], cwd=root / "desktop/src-tauri", text=True))
    active = {node["id"] for node in cargo["resolve"]["nodes"]}
    for package in cargo["packages"]:
        if package["id"] not in active or package["source"] is None:
            continue
        directory = Path(package["manifest_path"]).parent
        candidates = [path for path in directory.glob("*") if path.name.upper().startswith(NOTICE_PREFIXES)]
        if package.get("license_file"):
            candidate = directory / package["license_file"]
            if candidate.resolve().is_relative_to(directory.resolve()):
                candidates.append(candidate)
        provenance = None
        if args.fetch_missing and not any(path.is_file() for path in candidates):
            try:
                candidates, provenance = github_notices(package)
            except Exception as error:
                print(f"Could not fetch notices for {package['name']}: {type(error).__name__}")
        collect("cargo", package["name"], package["version"], package.get("license", "unknown"), candidates)
        if provenance:
            records[-1]["upstream"] = provenance
    report = {"schema": 1, "platform": "windows-x64", "records": records, "excluded_optional": excluded_optional,
              "missing_notices": sum(record["notice_missing"] for record in records), "complete": all(not record["notice_missing"] for record in records)}
    (output / "index.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Collected notices for {len(records)} dependencies; missing={report['missing_notices']}")


if __name__ == "__main__":
    main()

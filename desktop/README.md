# AI Config desktop 0.2.0 preview

> 当前入口（2026-10-08）：桌面客户端的备份、恢复与恢复记录；仅使用原样备份 ZIP。云端冻结，以下旧包与命令流程为历史参考。详见 [当前任务](../docs/desktop-offline-migration.md)。


Tauri 2 + React/TypeScript/Vite desktop shell and bundled Python 3.14 sidecar. Users do not install Python or Git for local/offline actions. Native installation and agent loading remain separate acceptance items.

Windows build from the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/build-desktop-sidecar.ps1
Set-Location desktop
npm ci
npm run tauri:build
```

Requires build-host Node.js 22.12+ or 24, Rust MSVC/C++ build tools and WebView2. This Windows build used Node.js 22.22.3; CI selects 24. Windows dependencies are resolved in requirements-windows.lock.txt. The sidecar contains only allowlisted common/templates/schemas/config templates, plus the Python core and libraries. It never packages developer home directories. The frontend controls only the named sidecar through the registered JSON Lines protocol. Installation artifacts appear in src-tauri/target/release/bundle/nsis; these are unsigned previews until clean-account installation succeeds.

macOS build must run on the matching real Mac with Python 3.14 and native toolchain:

```text
python3.14 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python ../scripts/build-desktop-sidecar.py --target aarch64-apple-darwin
npm ci
npm run tauri:build -- --config src-tauri/tauri.macos.conf.json
```

Use x86_64-apple-darwin only on an Intel Mac. Windows cannot validate this build. The manual CI workflow prepares Windows/ARM64 Mac unsigned artifacts; the workflow has not been run. ARM64/x64 support, signing and notarization remain unverified. macOS has a separate platform dependency resolution; the Windows lock is not a Mac lock.

0.2.0 includes existing local configuration and recovery pages, offline package selection/export/import, extension capture, and explicit cloud actions. Cloud requires a real HTTPS/OIDC deployment; the user chooses every action, previews and confirms. Python uses OS keyring for tokens/data keys. The application never treats cloud save or file application as proof of agent loading.

Create a manifest for the exact new artifact:

```text
python ../scripts/release-manifest.py --artifact <absolute-installer> --output <absolute-new-manifest.json>
```

The manifest reports source commit plus hashes of dirty/untracked source files; dirty development artifacts are not formal releases. Add `--notices <absolute-companion-archive>` to record its hash. `scripts/collect-release-notices.py --fetch-missing --output <new-directory>` collects installed Windows dependencies and pinned upstream Cargo notices. Distribute the companion archive with the installer. This run collected 322 entries with no missing notice files; cross-platform/server coverage, legal review and signed, clean-environment distribution remain release gates. The exact boundaries are in ../docs/third-party-licenses.md and ../docs/desktop-local-implementation.md.

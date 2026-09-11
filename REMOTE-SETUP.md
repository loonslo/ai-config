# Remote device setup

This repository contains shareable rules, synchronization code, schemas and a sanitized device template. It does not contain the current machine's full Codex or Claude configuration: those files can contain credentials, login state, provider settings, MCP commands and local runtime data.

## On the remote device

1. Clone this private repository.
2. Run the quick read-only check from the repository root:

```text
python scripts/sync.py quick
```

3. Review the JSON output, then apply the shareable rules:

```text
python scripts/sync.py quick --apply
```

This auto-detects the standard Codex and Claude directories and creates a Git-ignored local `device.json` only with `--apply`. It does not copy credentials, full tool configuration, or memory. Memory remains `not_run` until a private `ai-memory` repository and explicit mappings are configured.

4. Sign in to Codex and Claude on that device using their normal local flow. Do not copy `auth.json`, cookies, session databases or full tool configuration files.
5. If this device needs memory or custom paths, copy `examples/device.remote.json` to a local `device.json`, replace the `REPLACE_WITH_*` paths, keep `device` unique, and use the explicit commands below. Review previews first:

```text
python scripts/sync.py inventory --local device.json
python scripts/sync.py rules --local device.json
python scripts/sync.py config --local device.json
python scripts/sync.py memory --local device.json
```

6. Add `--apply` only after reviewing the listed paths and after closing sessions that may write memory.

The current project repository is available through GitHub, but no `ai-memory` remote has been configured or uploaded. Memory transfer therefore remains disabled until a separate private memory repository is intentionally provided. The Codex template is a reference configuration; it does not import Codex native memory databases.

Never commit the local `device.json`, full `~/.codex/config.toml`, full `~/.claude/settings.json`, credentials, cookies, session databases or plugin/runtime directories.

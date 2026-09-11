# Remote device setup

This repository contains shareable rules, synchronization code, schemas and a sanitized device template. It does not contain the current machine's full Codex or Claude configuration: those files can contain credentials, login state, provider settings, MCP commands and local runtime data.

## On the remote device

1. Clone this private repository.
2. Copy `examples/device.remote.json` to a local `device.json` outside Git.
3. Replace every `REPLACE_WITH_*` path with an absolute path on the remote device. Keep `device` unique for that machine.
4. Sign in to Codex and Claude on that device using their normal local flow. Do not copy `auth.json`, cookies, session databases or full tool configuration files.
5. Review previews first:

```text
python scripts/sync.py inventory --local device.json
python scripts/sync.py rules --local device.json
python scripts/sync.py config --local device.json
python scripts/sync.py memory --local device.json
```

6. Add `--apply` only after reviewing the listed paths and after closing sessions that may write memory.

The current project repository is available through GitHub, but no `ai-memory` remote has been configured or uploaded. Memory transfer therefore remains disabled until a separate private memory repository is intentionally provided. The Codex template is a reference configuration; it does not import Codex native memory databases.

Never commit the local `device.json`, full `~/.codex/config.toml`, full `~/.claude/settings.json`, credentials, cookies, session databases or plugin/runtime directories.

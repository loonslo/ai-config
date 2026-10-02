"""Configuration-only synchronization orchestration.

Pipeline (each stage reports its own failure so the user knows whether the
problem happened while downloading, applying or reporting):

    local drift check -> fetch remote -> resolve shared changes -> preview
    -> backup/apply -> verify target -> persist receipt

Configuration synchronization never requires ``ai-memory`` to exist.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable, Mapping

from . import config_status
from .config import DeviceConfig, managed_fields
from .status import build_state, capability
from .transaction import PlannedChanges, SyncLock, transaction


class ConfigSyncError(RuntimeError):
    """A stage-scoped failure with a stable stage name (and optional message code)."""

    def __init__(self, stage: str, message: str, *, exit_code: int = 1, code: str | None = None) -> None:
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code
        self.code = code


STAGES = ("drift", "fetch", "publish", "resolve", "apply", "verify", "receipt")

#: Repository root holding the shared templates.  Kept as a module constant so
#: tests can point it at a fixture checkout.
ROOT_FOR_TEMPLATES = Path(__file__).resolve().parents[1]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def local_drift(config: DeviceConfig, *, expected: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Compare the real target files against the projection the source produces."""
    raw = config.raw
    targets = config_status.scope_targets(raw)
    projections = expected or _expected_projections(config)
    records: list[dict[str, Any]] = []
    from .agents import RULES_KINDS
    from .load_check import extract_version, read_checks, state_of

    checks = read_checks(config.state_dir)
    for target in targets:
        key = (target["tool"], target["target_kind"])
        record = config_status.inspect_target(
            target,
            expected_projection=projections.get(key),
            last_applied_digest=_last_applied_digest(config, target),
        )
        if target["target_kind"] in RULES_KINDS:
            # The version this device should announce, and whether an agent was
            # shown to have loaded it (see ``verify-load``).
            version = extract_version(projections.get(key))
            record["rules_version"] = version
            record["load_check"] = state_of(checks.get(target["tool"]), version)
        records.append(record)
    drifted = [record for record in records if record["status"] == "local_modified"]
    return {
        "schema_version": 1,
        "checked_at": _now(),
        "targets": records,
        "drifting": drifted,
        "clean": not drifted,
        "summary": config_status.summarize(records),
        "unresolved": unresolved_agents(raw),
    }


def unresolved_agents(raw: Mapping[str, Any]) -> list[dict[str, str]]:
    """Registered agents that cannot receive rules yet, with the reason."""
    from .agents import agent_instances, unresolved_reason

    result = []
    for instance in agent_instances(raw):
        reason = unresolved_reason(instance)
        if reason:
            result.append({"instance": instance.id, "reason": reason})
    return result


#: A target only counts as verified when it matches the projection that was
#: written.  ``pending_sync`` means the target still holds an *older* version, so
#: accepting it here would report a successful apply for a file that was never
#: brought up to date.
VERIFIED_TARGET_STATUSES = frozenset({"applied"})
#: A target with an empty managed-field selection has nothing to verify; it is
#: not a failure, and must not make an otherwise successful apply look unverified.
EMPTY_SCOPE_STATUSES = frozenset({"not_configured", "pending_sync"})


def _targets_verified(targets: list[Mapping[str, Any]]) -> bool:
    """Whether every target either matches the expectation or has nothing managed."""
    for record in targets:
        if record.get("status") in VERIFIED_TARGET_STATUSES:
            continue
        if record.get("status") in EMPTY_SCOPE_STATUSES and not record.get("fields"):
            continue
        return False
    return True


def _unverified(targets: list[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [record for record in targets if not _record_verified(record)]


def _record_verified(record: Mapping[str, Any]) -> bool:
    if record.get("status") in VERIFIED_TARGET_STATUSES:
        return True
    return record.get("status") in EMPTY_SCOPE_STATUSES and not record.get("fields")


def _last_applied_digest(config: DeviceConfig, target: Mapping[str, Any]) -> str | None:
    marker = config.state_dir / "applied.json"
    if not marker.exists():
        return None
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    key = f"{target.get('tool')}:{target.get('target_kind')}"
    recorded = data.get("targets", {}).get(key)
    return recorded.get("digest") if isinstance(recorded, dict) else None


def _record_applied(config: DeviceConfig, targets: list[Mapping[str, Any]]) -> Path:
    from .utils import atomic_write, json_bytes

    marker = config.state_dir / "applied.json"
    records = {}
    for target in targets:
        key = f"{target.get('tool')}:{target.get('target_kind')}"
        records[key] = {
            "digest": target.get("observed_digest") or target.get("expected_digest"),
            "status": target.get("status"),
        }
    payload = {"schema_version": 1, "applied_at": _now(), "targets": records}
    atomic_write(marker, json_bytes(payload))
    return marker


def _expected_projections(config: DeviceConfig) -> dict[tuple[str, str], Any]:
    """What the shared source would write, computed independently of the target.

    The projection is derived from the repository templates rather than from a
    planner run over the current target: a target that was edited locally must
    still yield a comparable expectation instead of aborting the drift check.

    It must also be the *same* effective configuration the writer produces —
    the managed rules body including the memory index note, and this device's
    local overrides.  Anything else would make a successful apply fail its own
    read-back check.
    """
    from .planning import rules_body, source_root
    from .agents import managed_targets

    template_root = Path(source_root(config.raw, default_root=ROOT_FOR_TEMPLATES))
    projections: dict[tuple[str, str], Any] = {}
    for instance, entry in managed_targets(config.raw):
        # Each instance renders its own topic selection, exactly as the writer does.
        body = rules_body(config.raw, instance, default_root=ROOT_FOR_TEMPLATES)
        block, error = config_status.managed_block(body)
        projections[(instance.id, entry.kind)] = block if error is None else body

    overrides = effective_overrides(config.raw, config.state_dir)

    if config.raw.get("codex"):
        keys = tuple(managed_fields(config.raw).get("codex", []))
        projection: dict[str, Any] = {}
        if keys:
            try:
                import tomlkit
                template = tomlkit.parse((template_root / "codex/config.toml").read_text(encoding="utf-8"))
                projection = {key: str(template[key]) for key in keys if key in template}
            except (OSError, ValueError):
                projection = {}
        # The observed projection stringifies every managed value, so the
        # expectation has to as well.
        for key, value in overrides["codex"].items():
            if key in keys:
                projection[key] = str(value)
        projections[("codex", "config")] = projection

    if config.raw.get("claude"):
        keys = tuple(managed_fields(config.raw).get("claude", []))
        projection = {}
        if keys:
            try:
                document = json.loads((template_root / "claude/settings.shared.json").read_text(encoding="utf-8"))
                projection = {key: document[key] for key in keys if key in document}
            except (OSError, ValueError):
                projection = {}
        for key, value in overrides["claude"].items():
            if key in keys:
                projection[key] = value
        projections[("claude", "settings")] = projection
    return projections


def build_plan(config: DeviceConfig, *, apply: bool) -> tuple[PlannedChanges, dict[str, Any]]:
    """Resolve shared changes into a write plan without writing anything.

    A managed block that was edited locally into different content is reported
    as a conflict: the shared value is never silently written over it.
    """
    from .planning import config_plan, rules_plan

    state = config.state_dir
    metadata: dict[str, Any] = {"operation": "config"}
    changes: dict[Any, Any] = {}
    expected: dict[Any, Any] = {}
    for producer in (
        lambda raw, target_state: rules_plan(raw, target_state, default_root=ROOT_FOR_TEMPLATES),
        lambda raw, target_state: config_plan(raw, target_state, default_root=ROOT_FOR_TEMPLATES),
    ):
        try:
            produced = producer(config.raw, state)
        except ValueError as error:
            if "not owned by ai-config" in str(error):
                raise ConfigSyncError(
                    "resolve",
                    "目标位置已有一个不是由 ai-config 创建的文件，无法接管；先运行 migrate 处理已有内容。",
                    exit_code=4,
                    code="E3004",
                ) from error
            if "edited locally" in str(error) or "Invalid managed block" in str(error):
                raise ConfigSyncError(
                    "resolve",
                    "工具目标文件中的受管区块被本机直接修改，无法安全覆盖。",
                    exit_code=4,
                ) from error
            raise
        for path, data in produced.items():
            changes[path] = data
            if path in produced.expected:
                expected[path] = produced.expected[path]
        # The plan carries the decisions the producers made (for example the
        # one-shot rules restore intent) so the caller can act on them *after* a
        # verified apply instead of during planning.
        for key, value in produced.metadata.items():
            if key == "accepted_rules":
                metadata.setdefault("accepted_rules", [])
                metadata["accepted_rules"].extend(str(tool) for tool in value)
            elif key in {"path_agents", "created_dirs"}:
                metadata.setdefault(key, {})
                metadata[key].update(value)
    plan = PlannedChanges(changes, expected=expected, state_root=state, metadata=metadata)
    drift = local_drift(config)
    report = {
        "changes": len(plan),
        "paths": sorted(str(path) for path in plan),
        "drift": drift["summary"],
        "drifting": [record["target"] for record in drift["drifting"]],
    }
    return plan, report


def sync(
    config: DeviceConfig,
    *,
    apply: bool,
    fetch: Callable[[], Mapping[str, Any] | None] | None = None,
    publish: Callable[[bool], Mapping[str, Any]] | None = None,
    receipt: Callable[[], Mapping[str, Any]] | None = None,
    checkpoint: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """Run the configuration pipeline, reporting the failing stage explicitly.

    The stages map onto the three facts a user must be able to tell apart:
    ``fetch`` downloads the shared source, ``publish`` sends this device's own
    shared edits, ``apply``/``verify`` write and read back the local target
    files, and ``receipt`` reports the result to the other devices.
    """
    def note(stage: str) -> None:
        if checkpoint is not None:
            checkpoint(stage)

    def report_state() -> Mapping[str, Any] | None:
        """Report the outcome to the other devices; a failure is never fatal.

        The configuration is already applied and verified at this point, so a
        receipt that cannot be uploaded is reported as pending instead of
        turning a successful sync into an error.
        """
        if receipt is None:
            return None
        note("receipt")
        try:
            return receipt()
        except Exception as error:  # noqa: BLE001 - the config is already applied
            return {"status": "pending", "detail": f"状态上报失败：{error}"}

    note("drift")
    drift = local_drift(config)
    if drift["drifting"] and not apply:
        # A preview always shows drift; applying is still allowed because the
        # managed projection is what gets replaced, and the old value is backed up.
        pass

    note("fetch")
    remote_state: Mapping[str, Any] | None = None
    if fetch is not None:
        try:
            remote_state = fetch()
        except ConfigSyncError:
            raise
        except Exception as error:  # noqa: BLE001 - stage boundary
            raise ConfigSyncError("fetch", f"下载共享配置失败：{error}", exit_code=3) from error

    # Publishing is a write to the shared source, so it only ever runs as part of
    # an apply.  A preview reports what would be published and writes nothing.
    note("publish")
    publish_state: Mapping[str, Any] | None = None
    if publish is not None:
        try:
            publish_state = publish(apply)
        except ConfigSyncError:
            raise
        except Exception as error:  # noqa: BLE001 - stage boundary
            raise ConfigSyncError("publish", f"发布共享修改失败：{error}", exit_code=3) from error

    note("resolve")
    plan, resolved = build_plan(config, apply=apply)
    if not apply:
        return {
            "status": "preview",
            "ready": False,
            "stage": "preview",
            "changes": resolved["changes"],
            "paths": resolved["paths"],
            "drift": resolved["drift"],
            "drifting": resolved["drifting"],
            "remote": remote_state,
            "publish": publish_state,
            "unresolved": unresolved_agents(config.raw),
            "note": "预览不代表已经应用；零变更预览也不代表已生效。",
        }
    if not plan:
        # No change means no pointless write, but verification still runs.
        note("verify")
        verified = local_drift(config)
        if not _targets_verified(verified["targets"]):
            # Nothing was written and the targets still do not match, so this is
            # not an applied state: no success record is written.
            return {
                "status": "applied",
                "ready": False,
                "stage": "verify",
                "changes": 0,
                "drift": verified["summary"],
                "verified": False,
                "remote": remote_state,
                "publish": publish_state,
                "unresolved": unresolved_agents(config.raw),
                "note": "没有需要写入的变化，但目标文件仍未与共享值一致；未记录成功。",
            }
        _record_applied(config, verified["targets"])
        return {
            "status": "applied",
            "ready": True,
            "stage": "verify",
            "changes": 0,
            "drift": verified["summary"],
            "verified": True,
            "remote": remote_state,
            "publish": publish_state,
            "unresolved": unresolved_agents(config.raw),
            "receipt": report_state(),
            "note": "没有需要写入的变化；已重新核对目标文件。",
        }

    note("apply")
    try:
        # A single lock coordinates the whole apply. The transaction must not
        # take the lock again: the guard is an exclusive file lock, so an inner
        # acquisition in the same process would deadlock.
        with SyncLock(config.state_dir):
            transaction(plan, config.state_dir / "backups", state_root=config.state_dir, lock=False)
    except Exception as error:  # noqa: BLE001 - stage boundary
        raise ConfigSyncError("apply", f"写入目标文件失败：{error}", exit_code=1) from error

    note("verify")
    verified = local_drift(config)
    failed = [record for record in verified["targets"] if record["status"] == "apply_failed"]
    if failed:
        raise ConfigSyncError(
            "verify",
            "应用后无法核验目标文件，未生成成功回执：" + "、".join(str(record["target"]) for record in failed),
            exit_code=2,
        )
    unverified = _unverified(verified["targets"])
    if unverified:
        # The success record is written only after every target passed the
        # read-back check; otherwise the next run would treat a stale file as
        # applied just because it matches a version this device never verified.
        raise ConfigSyncError(
            "verify",
            "应用后目标文件仍与本机期望不一致，未生成成功回执："
            + "、".join(str(record["target"]) for record in unverified),
            exit_code=2,
        )
    _record_applied(config, verified["targets"])
    _consume_restore_intent(config, plan)
    record_created_dirs(config.state_dir, plan.metadata.get("created_dirs"))

    return {
        "status": "applied",
        "ready": True,
        "stage": "verify",
        "changes": len(plan),
        "verified": True,
        "requires_restart": True,
        "drift": verified["summary"],
        "remote": remote_state,
        "publish": publish_state,
        "unresolved": unresolved_agents(config.raw),
        "receipt": report_state(),
        "note": "本机目标文件已重新读取并核对一致；工具需要启动新会话才会加载。",
    }


CREATED_DIRS_FILE = "created_dirs.json"


def created_dirs(state_dir: Path) -> dict[str, list[str]]:
    """Directories ai-config created for owned files, per agent instance."""
    path = Path(state_dir) / CREATED_DIRS_FILE
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    dirs = data.get("dirs") if isinstance(data, dict) else None
    return {str(key): [str(item) for item in value] for key, value in (dirs or {}).items() if isinstance(value, list)}


def created_dirs_bytes(dirs: Mapping[str, list[str]]) -> bytes:
    from .utils import json_bytes

    return json_bytes({"schema_version": 1, "dirs": {key: value for key, value in sorted(dirs.items()) if value}})


def record_created_dirs(state_dir: Path, created: Mapping[str, list[str]] | None) -> None:
    """Remember newly created directories; an existing record is never shrunk here."""
    from .utils import atomic_write

    if not created:
        return
    dirs = created_dirs(state_dir)
    for instance, paths in created.items():
        known = dirs.setdefault(instance, [])
        for path in paths:
            if path not in known:
                known.append(path)
    atomic_write(Path(state_dir) / CREATED_DIRS_FILE, created_dirs_bytes(dirs))


def _consume_restore_intent(config: DeviceConfig, plan: PlannedChanges) -> None:
    """Clear a one-shot rules restore intent only after a verified apply.

    The planner records the accepted intent in the plan metadata instead of
    clearing it itself, so a preview stays read-only and a failed apply does not
    silently drop the user's decision.
    """
    for tool in plan.metadata.get("accepted_rules", []) or []:
        clear_accept_shared(config, str(tool))


def state_for(config: DeviceConfig, *, remote_ok: bool | None = None) -> dict[str, Any]:
    """Produce the local state document used by ``status`` and receipts."""
    from .config_source import source_root
    from .handoff import configuration_facts

    drift = local_drift(config)
    facts = configuration_facts(source_root(config.raw))
    statuses = {record["status"] for record in drift["targets"]}
    if "apply_failed" in statuses:
        config_status_code = "apply_failed"
    elif "local_modified" in statuses:
        config_status_code = "local_modified"
    elif "conflict" in statuses:
        config_status_code = "conflict"
    elif not drift["targets"]:
        config_status_code = "not_configured"
    elif remote_ok is False:
        config_status_code = "offline"
    elif "pending_sync" in statuses or "not_configured" in statuses:
        config_status_code = "pending_sync"
    else:
        config_status_code = "applied"

    source_status = "applied" if config_status_code == "applied" else config_status_code
    if not config.raw.get("remote_identity"):
        source_status = "not_configured"
    managed = {
        "shared_fields": managed_fields(config.raw),
        "targets": drift["targets"],
        "last_applied_version": facts.get("version"),
        "last_applied_at": _last_applied_at(config),
        "last_verified_at": drift["checked_at"],
    }
    return build_state(
        device_id=config.device,
        source={
            "type": "git" if config.raw.get("remote_identity") else "local",
            "identity": config.raw.get("remote_identity"),
            "url": config.raw.get("remote_url"),
            "branch": facts.get("branch"),
            "commit": facts.get("commit"),
            "remote_commit": facts.get("remote_commit"),
            "dirty_files": facts.get("dirty_files", []),
            "status": source_status,
        },
        capabilities={
            "config": capability(enabled=True, status=config_status_code, checked_at=drift["checked_at"]),
            "memory": capability(
                enabled=bool(config.raw.get("memories") or config.raw.get("codex_memory")),
                status="not_configured" if not (config.raw.get("memories") or config.raw.get("codex_memory")) else "pending_sync",
            ),
            "handoff": capability(enabled=bool(config.raw.get("projects")), status="not_configured" if not config.raw.get("projects") else "pending_sync"),
        },
        managed=managed,
    )


def _last_applied_at(config: DeviceConfig) -> str | None:
    marker = config.state_dir / "applied.json"
    if not marker.exists():
        return None
    try:
        return json.loads(marker.read_text(encoding="utf-8")).get("applied_at")
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# TASK-12: persist the ownership choice for a differing managed field
# --------------------------------------------------------------------------

#: Template files that may be updated by a "share" choice, and the key path
#: inside them.  Only these files are ever committed — never the whole workspace.
SHARE_TEMPLATES = {
    "codex": Path("codex/config.toml"),
    "claude": Path("claude/settings.shared.json"),
}

#: Local override files live under the state directory, so a "this device only"
#: choice is never published to other machines.
LOCAL_OVERRIDE_FILE = "local_overrides.json"


class OwnershipError(RuntimeError):
    """The chosen ownership could not be persisted safely."""

    def __init__(self, message: str, *, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _local_override_path(config: DeviceConfig) -> Path:
    return config.state_dir / LOCAL_OVERRIDE_FILE


def _share_template_root(config: DeviceConfig) -> Path:
    """Where a shared value is written.

    A device that recorded ``config_repo`` shares into that checkout, so the
    value it publishes is the value the other devices download.  Otherwise the
    templates the scripts were loaded from are used.
    """
    if config.raw.get("config_repo"):
        from .config_source import source_root

        return source_root(config.raw)
    return Path(ROOT_FOR_TEMPLATES)


def read_local_overrides(config: DeviceConfig) -> dict[str, dict[str, Any]]:
    """Read this device's local overrides; missing file means empty."""
    path = _local_override_path(config)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def local_override_values(raw: Mapping[str, Any], state_dir: Path) -> dict[str, dict[str, Any]]:
    """The overrides recorded by the ``local`` ownership choice, read from disk."""
    empty = {tool: {} for tool in SHARE_TEMPLATES}
    path = Path(state_dir) / LOCAL_OVERRIDE_FILE
    if not path.exists():
        return empty
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return empty
    if not isinstance(data, Mapping):
        return empty
    result: dict[str, dict[str, Any]] = {}
    for tool in SHARE_TEMPLATES:
        entry = data.get(tool)
        result[tool] = dict(entry) if isinstance(entry, Mapping) else {}
    return result


def effective_overrides(raw: Mapping[str, Any], state_dir: Path) -> dict[str, dict[str, Any]]:
    """Every device-local override that has to win over the shared template.

    Two sources exist: the ``{tool}_overrides`` block written by hand in
    ``device.json``, and ``local_overrides.json`` written by the ``local``
    ownership choice.  The recorded choice is the more recent explicit decision,
    so it wins — and it is what makes "仅此设备" survive the next sync instead of
    being silently replaced by the shared value.
    """
    recorded = local_override_values(raw, state_dir)
    result: dict[str, dict[str, Any]] = {}
    for tool in SHARE_TEMPLATES:
        merged = dict(raw.get(f"{tool}_overrides", {}) or {})
        merged.update(recorded[tool])
        result[tool] = merged
    return result


def plan_ownership(
    config: DeviceConfig,
    *,
    tool: str,
    field_name: str,
    value: Any,
    choice: str,
    apply: bool,
) -> dict[str, Any]:
    """Describe, and optionally persist, one ownership decision.

    Nothing is written on a preview.  A sensitive value is never allowed into a
    shared template, and a ``share`` choice only touches the managed key inside
    the template file rather than committing the workspace.
    """
    from .diff_view import CHOICES, is_sensitive_value

    if choice not in CHOICES:
        raise OwnershipError(f"未知的处理方式：{choice}；可选：{'、'.join(CHOICES)}")
    if tool not in SHARE_TEMPLATES:
        raise OwnershipError(f"不支持的工具：{tool}")

    if choice in {"share", "local"} and is_sensitive_value(field_name, value):
        raise OwnershipError("该字段可能是凭据或会话信息，不能共享，也不会写入覆盖文件。", exit_code=4)
    if isinstance(value, (dict, list)):
        raise OwnershipError("该字段是复杂结构，第一版只能显示，不能自动保存归属选择。", exit_code=4)
    if choice in {"share", "local"} and value is None:
        # Writing a null would either fail to parse or erase the value for every
        # device; neither is "keep/share this device's value".
        raise OwnershipError(
            "本机没有可保存的值（本机覆盖为空）；请先让本机文件里存在该字段，或改用 restore 采用共享值。",
            exit_code=4,
        )

    if choice == "share":
        target_path = _share_template_root(config) / SHARE_TEMPLATES[tool]
        result = {
            "choice": "share",
            "tool": tool,
            "field": field_name,
            "target": str(target_path),
            "value": value,
            "committed_files": [SHARE_TEMPLATES[tool].as_posix()],
            "effect": "只更新共享模板中的受管字段；还需要运行 sync --publish 发布到配置源远端，其他设备下次同步后才得到该值。",
        }
        if not apply:
            result["status"] = "preview"
            result["written"] = False
            return result
        result["backup"] = _write_template_value(
            _share_template_root(config), tool, field_name, value, state_dir=config.state_dir
        )
        result.update({"status": "saved", "written": True})
        return result

    if choice == "local":
        overrides = read_local_overrides(config)
        entry = overrides.setdefault(tool, {})
        result = {
            "choice": "local",
            "tool": tool,
            "field": field_name,
            "target": str(_local_override_path(config)),
            "value": value,
            "committed_files": [],
            "effect": "写入本机覆盖，只影响这台设备，不修改共享模板，也不会被提交。",
        }
        if not apply:
            result["status"] = "preview"
            result["written"] = False
            return result
        entry[field_name] = value
        result["backup"] = _write_local_overrides(config, overrides)
        result.update({"status": "saved", "written": True})
        return result

    # restore: the shared value is applied to this device by the normal apply
    # path (with backup), so ownership itself writes nothing here.
    return {
        "choice": "restore",
        "tool": tool,
        "field": field_name,
        "target": str(config.state_dir / "applied.json"),
        "value": value,
        "committed_files": [],
        "effect": "由配置同步先备份再应用共享值；本机当前值可在 restore 中找回。",
        "status": "preview" if not apply else "delegated",
        "written": False,
    }


def _write_template_value(root: Path, tool: str, field_name: str, value: Any, *, state_dir: Path) -> str | None:
    """Update one managed key in a shared template with a recoverable backup."""
    from .utils import digest

    path = Path(root) / SHARE_TEMPLATES[tool]
    if path.is_symlink():
        raise OwnershipError("共享规则模板是符号链接；未写入内容。", exit_code=4)
    current = path.read_bytes()
    text = current.decode("utf-8")
    if tool == "codex":
        try:
            import tomlkit
        except ImportError as error:  # pragma: no cover - dependency declared
            raise OwnershipError("缺少 tomlkit，无法更新共享模板。") from error
        document = tomlkit.parse(text)
        document[field_name] = value
        updated = tomlkit.dumps(document).encode("utf-8")
    else:
        document = json.loads(text)
        document[field_name] = value
        updated = (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    plan = PlannedChanges(
        {path: updated},
        expected={path: digest(current)},
        state_root=state_dir,
        metadata={"operation": "diff-share", "path_agents": {}},
    )
    backup = transaction(plan, state_dir / "backups", state_root=state_dir)
    return str(backup) if backup else None


def _write_local_overrides(config: DeviceConfig, overrides: Mapping[str, Any]) -> str | None:
    from .utils import digest, json_bytes, read_bytes

    path = _local_override_path(config)
    current = read_bytes(path)
    plan = PlannedChanges(
        {path: json_bytes(dict(overrides))},
        expected={path: digest(current)},
        state_root=config.state_dir,
        metadata={"operation": "diff-local", "path_agents": {}},
    )
    backup = transaction(plan, config.state_dir / "backups", state_root=config.state_dir)
    return str(backup) if backup else None


def plan_rules_ownership(
    config: DeviceConfig,
    *,
    tool: str,
    choice: str,
    apply_choice: bool,
    drifting: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve a hand-edited managed rules block.

    The rules planner refuses to overwrite an edited block, so the user has to
    decide.  Unlike a scalar field there is no "merge": the two safe options are

    * ``share`` — adopt the local block as the shared value, so the other
      devices receive it on their next sync;
    * ``restore`` — accept the shared block and overwrite the local edit
      (after a backup).

    ``local`` is not offered: keeping a divergent rules block on one device
    while telling every other device the shared value is current is exactly the
    silent divergence the rewritten rules block cannot represent.
    """
    from .diff_view import is_sensitive_value

    if choice == "local":
        raise OwnershipError(
            "受管规则区块不能只保留在本机；请选择 share（把本机版本作为共享值）或 restore（恢复共享值）。",
            exit_code=4,
        )
    if choice not in {"share", "restore"}:
        raise OwnershipError(f"未知的处理方式：{choice}；规则区块可选：share、restore", exit_code=4)

    targets = [str(record.get("target")) for record in drifting if record.get("tool") == tool]
    if not targets:
        return {
            "choice": choice,
            "tool": tool,
            "field": "rules",
            "status": "no_changes",
            "written": False,
            "committed_files": [],
            "effect": "该工具的受管规则区块没有被本机修改，无需处理。",
        }

    if choice == "share":
        result = {
            "choice": "share",
            "tool": tool,
            "field": "rules",
            "target": targets,
            "committed_files": ["common/"],
            "effect": (
                "把本机受管区块登记为共享版本：请把本机区块内容合并进 common/ 下对应主题文件，"
                "再运行 sync --publish 发布到配置源远端；其他设备下次同步后得到该内容。"
            ),
        }
        if not apply_choice:
            result["status"] = "preview"
            result["written"] = False
            return result
        # The shared prose lives in ``common/``; the tool cannot split an
        # aggregated block back into topic files, so the local block content is
        # staged for the merge instead of being declared done.  The recorded
        # baseline is deliberately *not* refreshed: until the shared source
        # really produces this block, the divergence must stay visible.
        staged = _stage_local_block(config, tool)
        result.update({
            "status": "pending_publish",
            "written": True,
            "staged_content": str(staged) if staged else None,
            "effect": (
                "本机受管区块内容已保存为待合并文件，冲突保护保留："
                "把该内容合并进 common/ 下对应主题文件，运行 sync --publish 发布，"
                "再运行一次 sync 确认共享值与本机一致。"
            ),
        })
        return result

    result = {
        "choice": "restore",
        "tool": tool,
        "field": "rules",
        "target": targets,
        "committed_files": [],
        "effect": "先备份本机文件，再把共享规则区块写回；本机当前内容可在 undo 中找回。",
    }
    if not apply_choice:
        result["status"] = "preview"
        result["written"] = False
        return result
    # `restore` deliberately writes nothing here: clearing the recorded block
    # hash makes the shared block authoritative again, and the normal apply path
    # then backs up and rewrites the file with verification.
    _accept_shared_block(config, tool)
    result.update({"status": "saved", "written": True})
    return result


def _stage_local_block(config: DeviceConfig, tool: str) -> Path | None:
    """Keep the local managed block content so it can be merged into ``common/``.

    Nothing is written into the repository: the staged copy lives under the
    device state directory, and the shared source only changes once a human
    merges the prose and publishes it.
    """
    from .agents import managed_targets
    from .config_status import managed_block
    from .utils import atomic_write

    entry = next((target for instance, target in managed_targets(config.raw) if instance.id == tool), None)
    if entry is None or not entry.path.exists():
        return None
    block, error = managed_block(entry.path.read_bytes())
    if error is not None or block is None:
        return None
    staged = config.state_dir / "rules-share" / f"{tool}-{entry.path.name}.block.md"
    atomic_write(staged, block)
    return staged


def _accept_shared_block(config: DeviceConfig, tool: str) -> None:
    """Record the one-shot intent to let the shared block overwrite the local one.

    The block itself is not written here.  Recording the intent makes the planner
    accept the shared body on the next run, where the normal apply path backs the
    file up and the read-back verification confirms the result.  The marker is
    consumed only after that verified apply (``_consume_restore_intent``), so a
    preview never spends the user's decision.
    """
    from .utils import atomic_write, json_bytes

    atomic_write(_accept_marker_path(config, tool), json_bytes({"schema_version": 1, "accept_shared": True}))


def _accept_marker_path(config: DeviceConfig, tool: str) -> Path:
    return config.state_dir / f"{tool}-rules-accept-shared.json"


def rules_accept_shared(config: DeviceConfig, tool: str) -> bool:
    """Whether the user asked to overwrite the local rules block with the shared one."""
    path = _accept_marker_path(config, tool)
    if not path.exists():
        return False
    try:
        return bool(json.loads(path.read_text(encoding="utf-8")).get("accept_shared"))
    except (OSError, ValueError):
        return False


def clear_accept_shared(config: DeviceConfig, tool: str) -> None:
    """Consume the one-shot restore intent once the shared block was applied."""
    path = _accept_marker_path(config, tool)
    try:
        path.unlink()
    except OSError:
        pass

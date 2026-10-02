"""Explicit portable extensions; never crawl an entire agent runtime directory."""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import tomllib
from typing import Any, Mapping
from urllib.parse import quote, unquote, urlsplit

from ..merge import validate_file_map
from ..transaction import PlannedChanges, transaction
from ..utils import digest
from .conflicts import _file_bytes
from .policy import CollectionReport, PolicyIssue, PortableEntry, _text_policy_issue

ADAPTERS = {"skills_v1": 1, "mcp_v1": 1, "memory_portable_v1": 1, "handoff_portable_v1": 1}
KINDS = {"skills": ("skill", "skill_file", "skills_v1"), "mcp": ("mcp", "mcp_config", "mcp_v1"),
         "memory": ("memory", "memory_snapshot", "memory_portable_v1"),
         "handoffs": ("handoff", "handoff_record", "handoff_portable_v1")}
MAX_FILES = 1024
MAX_BYTES = 32 * 1024 * 1024
_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")
_TEXT_SUFFIXES = {".md", ".txt", ".json", ".toml", ".yaml", ".yml", ".py", ".js", ".ts", ".sh", ".ps1", ".css", ".html", ".svg", ".csv"}
_HANDOFF_PREFIX = "<!-- ai-config portable handoff v1: "


def handoff_reference(content: bytes, project_id: str, handoff_id: str) -> tuple[dict[str, Any], str]:
    text = content.decode("utf-8")
    header, separator, document = text.partition("\n")
    if not separator or not header.startswith(_HANDOFF_PREFIX) or not header.endswith(" -->") or len(content) > 128 * 1024:
        raise ValueError("可移植交接头或体积无效。")
    value = json.loads(header[len(_HANDOFF_PREFIX):-4])
    if not isinstance(value, dict) or set(value) != {"project_id", "handoff_id", "commit", "branch", "lock_files", "memory_snapshot", "ready"}:
        raise ValueError("可移植交接元数据无效。")
    if value["project_id"] != project_id or value["handoff_id"] != handoff_id or value["ready"] is not False:
        raise ValueError("可移植交接身份无效。")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,127}", handoff_id):
        raise ValueError("交接 ID 无效。")
    for key in ("commit", "memory_snapshot"):
        item = value[key]
        pattern = r"[a-f0-9]{40}|[a-f0-9]{64}" if key == "commit" else r"[a-z0-9][a-z0-9_-]{0,127}"
        if item is not None and (not isinstance(item, str) or not re.fullmatch(pattern, item)):
            raise ValueError("源码版本或快照身份无效。")
    if value["branch"] is not None and (not isinstance(value["branch"], str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,128}", value["branch"])):
        raise ValueError("源码分支无效。")
    locks = value["lock_files"]
    if not isinstance(locks, dict) or len(locks) > 32 or any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name) or not isinstance(sha, str) or not re.fullmatch(r"[a-f0-9]{64}", sha) for name, sha in locks.items()):
        raise ValueError("依赖锁文件身份无效。")
    return value, document


def capabilities() -> list[dict[str, Any]]:
    return [
        {"kind": kind, "data_type": spec[1], "adapter": spec[2], "implemented": True,
         "verified_agent": False, "detail": detail}
        for kind, spec, detail in [
            ("skills", KINDS["skills"], "Codex / Claude 技能复制部署；只选定技能，外部链接拒绝；Agent 实机识别待验收"),
            ("mcp", KINDS["mcp"], "Codex stdio / HTTP 非敏感配置；只保留变量名；连接需单独验证"),
            ("memory", KINDS["memory"], "Claude Markdown / Codex 参考快照；导入配置库后选择本机项目映射"),
            ("handoffs", KINDS["handoffs"], "已校验交接文档；保留源码版本，缺少源码不标记完整接续"),
        ]
    ]


def _portable_text(name: str, data: bytes) -> None:
    issue = _text_policy_issue(name, data, local_roots=())
    if issue is not None:
        raise ValueError("所选内容含疑似凭据、本机路径或不支持的编码；请先在本机处理。")


def read_skill(root: Path, boundary: Path) -> dict[str, bytes]:
    """Resolve links only within the explicitly selected agent skills boundary."""
    if any(path.is_symlink() or getattr(path, "is_junction", lambda: False)() for path in (boundary, *boundary.parents)):
        raise ValueError("技能根目录由外部链接管理；请保留现有管理者，不能越界采集。")
    boundary = boundary.resolve(strict=True)
    files: dict[str, bytes] = {}
    seen: set[Path] = set()
    total = 0

    def visit(path: Path, relative: str) -> None:
        nonlocal total
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(boundary):
            raise ValueError("技能链接越出所选 Agent 的 skills 范围。")
        if resolved in seen:
            raise ValueError("技能链接循环或重复目录。")
        if resolved.is_dir():
            seen.add(resolved)
            for child in sorted(resolved.iterdir()):
                if child.name.startswith(".") or child.name in {"node_modules", "__pycache__"}:
                    raise ValueError("技能含隐藏或运行目录；请先清理选择范围。")
                visit(child, f"{relative}/{child.name}" if relative else child.name)
            seen.remove(resolved)
        else:
            if resolved.suffix.casefold() not in _TEXT_SUFFIXES:
                raise ValueError("技能含未支持的二进制资源，不能声称完整采集。")
            data = _file_bytes(resolved, limit=MAX_BYTES)
            if data is None:
                raise ValueError("技能来源已失联。")
            total += len(data)
            if len(files) >= MAX_FILES or total > MAX_BYTES:
                raise ValueError("技能超出文件数或体积上限。")
            _portable_text(relative, data)
            files[relative] = data

    visit(root, "")
    if "SKILL.md" not in files:
        raise ValueError("选择的技能没有 SKILL.md。")
    first = validate_file_map(files)
    files = {}
    total = 0
    seen.clear()
    visit(root, "")
    if first != validate_file_map(files):
        raise ValueError("技能在采集中变化；没有保存混合版本。")
    return first


def normalize_mcp(value: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {"command", "args", "env", "env_vars", "url", "bearer_token_env_var", "enabled", "startup_timeout_sec", "tool_timeout_sec"}
    if set(value) - allowed:
        raise ValueError("MCP 含未知字段或凭据字段，拒绝迁移。")
    if bool(value.get("command")) == bool(value.get("url")):
        raise ValueError("MCP 必须选择一个 stdio 命令或 HTTP URL。")
    env = value.get("env", {})
    names = value.get("env_vars", [])
    if not isinstance(env, Mapping) or not isinstance(names, list):
        raise ValueError("MCP 环境变量形态无效。")
    if any(not isinstance(name, str) or not _ENV.fullmatch(name) for name in [*env, *names]):
        raise ValueError("MCP 环境变量名无效。")
    # Inline values are never read into an export; a variable-reference-only
    # source must be prepared locally before it can enter a migration package.
    if env:
        raise ValueError("MCP 含内嵌环境变量值；请先改为 env_vars 引用。")
    result = {key: value[key] for key in ("command", "args", "url", "bearer_token_env_var", "enabled", "startup_timeout_sec", "tool_timeout_sec") if key in value}
    result["env_vars"] = sorted(set(names))
    for field in ("startup_timeout_sec", "tool_timeout_sec"):
        if field in result and (type(result[field]) not in {int, float} or not 0 < result[field] <= 3600):
            raise ValueError("MCP 超时必须是有界正数。")
    if "enabled" in result and not isinstance(result["enabled"], bool):
        raise ValueError("MCP enabled 必须是布尔值。")
    if "bearer_token_env_var" in result and (not isinstance(result["bearer_token_env_var"], str) or not _ENV.fullmatch(result["bearer_token_env_var"])):
        raise ValueError("MCP 凭据只能使用有效环境变量名称。")
    if "command" in result and (not isinstance(result["command"], str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", result["command"])):
        raise ValueError("本机命令路径不可携带；仅支持目标机 PATH 中的命令名。")
    args = result.get("args", [])
    if not isinstance(args, list) or any(not isinstance(arg, str) or len(arg) > 2048 or re.search(r"(?i)(token|password|secret|api[_-]?key)|[A-Za-z]:[\\/]|(?:^|=)/|~/", arg) or Path(arg).is_absolute() for arg in args):
        raise ValueError("MCP 参数含凭据、绝对路径或未知形态。")
    if "url" in result:
        url = urlsplit(result["url"])
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError("MCP URL 仅支持不含凭据、查询串的 HTTPS 地址。")
    _portable_text("mcp.json", json.dumps(result).encode())
    return result


def validate_extension(logical: str, data_type: str, adapter: str, content: bytes) -> tuple[str, str, list[str]]:
    uri = urlsplit(logical)
    parts = [unquote(part, errors="strict") for part in uri.path.lstrip("/").split("/")]
    kind = next((key for key, value in KINDS.items() if value == (uri.scheme, data_type, adapter)), None)
    if kind is None or uri.netloc not in {"codex", "claude"} or len(parts) < 2 or not _NAME.fullmatch(parts[0]):
        raise ValueError("扩展内容来源或适配器不匹配。")
    validate_file_map({"/".join(parts): content})
    if any(part.startswith(".") for part in parts):
        raise ValueError("扩展内容禁止隐藏路径。")
    _portable_text(logical, content)
    if kind == "mcp":
        if uri.netloc != "codex" or parts[1:] != ["config.json"]:
            raise ValueError("MCP 当前仅支持 Codex。")
        value = json.loads(content)
        if not isinstance(value, dict) or normalize_mcp(value) != value:
            raise ValueError("MCP 内容不符合非敏感协议。")
    if kind in {"memory", "handoffs"} and parts[-1].endswith(".md") is False:
        raise ValueError("记忆和交接仅支持 Markdown。")
    if kind == "handoffs":
        if len(parts) != 2:
            raise ValueError("交接必须是项目内的单个记录。")
        handoff_reference(content, parts[0], parts[1][:-3])
    return kind, uri.netloc, parts


def collect_extensions(store: Path, report: CollectionReport, kinds: list[str]) -> CollectionReport:
    entries = list(report.entries)
    issues = list(report.unsupported)
    fingerprints = list(report.source_fingerprints)
    for kind in kinds:
        if kind not in KINDS:
            raise ValueError("未知迁移范围。")
        root = store / "portable" / kind
        if not root.exists():
            continue
        # Store content must be real regular files; links are resolved at the
        # explicit capture boundary, never during an unattended export scan.
        if any(path.is_symlink() or getattr(path, "is_junction", lambda: False)() for path in (root, *root.parents)):
            raise ValueError("扩展配置库根目录含链接。")
        paths = []
        for path in root.rglob("*"):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("扩展配置库含链接。")
            paths.append(path)
            if len(paths) > MAX_FILES:
                raise ValueError("扩展配置库超过文件数量上限。")
        seen_names: dict[str, bytes] = {}
        total = 0
        for path in sorted(paths):
            if path.is_symlink() or getattr(path, "is_junction", lambda: False)():
                raise ValueError("扩展配置库含链接。")
            if not path.is_file():
                continue
            relative = path.relative_to(root).as_posix()
            profile, *parts = relative.split("/")
            spec = KINDS[kind]
            logical = f"{spec[0]}://{profile}/" + "/".join(quote(part, safe="-._~") for part in parts)
            data = _file_bytes(path, limit=MAX_BYTES)
            if data is None:
                raise ValueError("扩展来源采集中消失。")
            total += len(data)
            if total > MAX_BYTES:
                raise ValueError("扩展范围超出体积上限。")
            seen_names[relative] = data
            try:
                validate_extension(logical, spec[1], spec[2], data)
            except ValueError:
                issues.append(PolicyIssue(logical, "unsupported", "扩展内容未通过可移植安全检查"))
                continue
            entries.append(PortableEntry(logical, spec[1], spec[2], 1, data))
            fingerprints.append((logical, hashlib.sha256(data).hexdigest()))
        validate_file_map(seen_names)
    return replace(report, entries=tuple(sorted(entries, key=lambda item: item.logical_source)),
                   unsupported=tuple(issues), source_fingerprints=tuple(sorted(fingerprints)))


def capture(config: Mapping[str, Any], store: Path, *, kind: str, profile: str, name: str,
            source: Path, apply: bool = False) -> tuple[dict[str, Any], PlannedChanges]:
    if kind not in KINDS or profile not in {"codex", "claude"} or not _NAME.fullmatch(name):
        raise ValueError("扩展类型、Agent 或逻辑名称无效。")
    from ..agents import agent_instances
    instances = [item for item in agent_instances(config) if item.profile.id == profile]
    source = source.expanduser().absolute()
    if kind == "skills":
        boundary = next((item.root / "skills" for item in instances if source.parent == item.root / "skills"), None)
        if boundary is None:
            raise ValueError("请选择已登记 Agent 的 skills 目录中的单个技能。")
        files = read_skill(source, boundary)
    elif kind == "mcp":
        if profile != "codex" or not any(source == item.root / "config.toml" for item in instances):
            raise ValueError("MCP 来源必须是已登记 Codex 的 config.toml。")
        raw = _file_bytes(source)
        servers = tomllib.loads((raw or b"").decode()).get("mcp_servers", {})
        if name not in servers or not isinstance(servers[name], dict):
            raise ValueError("所选 MCP 服务不存在。")
        files = {"config.json": json.dumps(normalize_mcp(servers[name]), ensure_ascii=False, sort_keys=True).encode()}
    elif kind == "memory":
        from ..config import absolute
        from ..snapshots import _manifest_hash
        repo = absolute(config["memory_repo"])
        if source.suffix != ".json" or source.parent.parent != repo / "snapshots":
            raise ValueError("请选择已登记记忆库的可校验快照清单。")
        snapshot = json.loads(_file_bytes(source) or b"null")
        if not isinstance(snapshot, dict) or snapshot.get("schema_version") != 1 or snapshot.get("snapshot_id") != source.stem or snapshot.get("device_id") != source.parent.name or snapshot.get("manifest_sha256") != _manifest_hash(snapshot):
            raise ValueError("快照身份或清单校验失败。")
        if snapshot.get("tool") != profile:
            raise ValueError("快照 Agent 与选择不一致。")
        if name != (snapshot.get("project_id") or snapshot.get("scope")):
            raise ValueError("项目 ID 必须保持快照逻辑身份，不能重命名为另一项目。")
        files = {}
        for item in snapshot.get("files", []):
            object_name = item.get("object", "")
            if not re.fullmatch(r"objects/[a-f0-9]{64}\.md", object_name):
                raise ValueError("快照对象路径不在允许范围。")
            data = _file_bytes(repo / object_name)
            if data is None or len(data) != item.get("size") or digest(data) != item.get("sha256") or item.get("path") in files:
                raise ValueError("快照对象完整性或身份校验失败。")
            files[item["path"]] = data
    else:
        from ..config import absolute
        repo = absolute(config["memory_repo"])
        if source.suffix != ".json" or source.parent.parent != repo / "handoffs" or source.parent.name != name:
            raise ValueError("请选择已登记项目的交接清单。")
        record = json.loads(_file_bytes(source) or b"null")
        if not isinstance(record, dict) or record.get("schema_version") != 1 or record.get("project_id") != name or record.get("handoff_id") != source.stem:
            raise ValueError("交接清单身份无效。")
        document = _file_bytes(source.with_suffix(".md"))
        if document is None or hashlib.sha256(document).hexdigest() != record.get("document_sha256"):
            raise ValueError("交接文档内容校验失败。")
        _portable_text("handoff.md", document)
        # Reference metadata remains text; the receiver cannot infer that source
        # code is present or that an imported handoff has remote confirmation.
        code = record.get("code", {})
        reference = {"project_id": name, "handoff_id": source.stem, "commit": code.get("commit"),
                     "branch": code.get("branch"), "lock_files": code.get("lock_files", {}),
                     "memory_snapshot": record.get("memory_snapshot"), "ready": False}
        header = _HANDOFF_PREFIX + json.dumps(reference, ensure_ascii=False, sort_keys=True) + " -->\n"
        files = {f"{source.stem}.md": header.encode() + document}
    files = validate_file_map(files)
    desired: dict[Path, bytes] = {}
    expected: dict[Path, str | None] = {}
    spec = KINDS[kind]
    for relative, data in files.items():
        logical = f"{spec[0]}://{profile}/{name}/" + "/".join(quote(part, safe="-._~") for part in relative.split("/"))
        validate_extension(logical, spec[1], spec[2], data)
        target = store / "portable" / kind / profile / name / relative
        old = _file_bytes(target)
        expected[target] = digest(old)
        if old is not None and old != data:
            raise ValueError("配置库已有不同扩展内容；请选择新的逻辑名称，原件保留。")
        if old != data:
            desired[target] = data
    plan = PlannedChanges(desired, expected=expected, state_root=Path(config["state_dir"]), metadata={"operation": "migrate"})
    source_digest = hashlib.sha256(b"".join(name.encode() + hashlib.sha256(data).digest() for name, data in sorted(files.items()))).hexdigest()
    result = {"status": "ready", "can_apply": bool(plan), "kind": kind, "file_count": len(files),
              "source_digest": source_digest, "note": "仅保存配置库；未部署、执行或连接 Agent。"}
    if apply and plan:
        backup = transaction(plan, Path(config["state_dir"]) / "backups", state_root=Path(config["state_dir"]))
        result.update(status="captured", backup_created=backup is not None)
    return result, plan


def mcp_dependencies(content: bytes) -> list[str]:
    import os
    value = json.loads(content)
    missing = [f"环境变量 {name}" for name in [*value.get("env_vars", []), *([value["bearer_token_env_var"]] if value.get("bearer_token_env_var") else [])] if not os.environ.get(name)]
    if value.get("command") and shutil.which(value["command"]) is None:
        missing.append(f"命令 {value['command']}")
    return missing


def portable_project_report(config: Mapping[str, Any], store: Path, *, project_id: str, profile: str,
                            handoff_id: str | None = None) -> dict[str, Any]:
    """Inspect saved references without Git fetch, source execution, or writes."""
    from ..config import absolute
    from ..handoff import _git, repo_root
    if not _NAME.fullmatch(project_id) or profile not in {"claude", "codex"}:
        raise ValueError("请选择有效的项目 ID 和 Agent。")
    report = collect_extensions(store, CollectionReport((), (), (), (), 0), ["memory", "handoffs"])
    memories = [entry for entry in report.entries if entry.logical_source.startswith(f"memory://{profile}/{project_id}/")]
    records = []
    selected = None
    for entry in report.entries:
        prefix = f"handoff://{profile}/{project_id}/"
        if not entry.logical_source.startswith(prefix):
            continue
        identity = unquote(entry.logical_source[len(prefix):])[:-3]
        reference, document = handoff_reference(entry.content, project_id, identity)
        records.append({"handoff_id": identity, "commit": reference["commit"], "branch": reference["branch"]})
        if identity == handoff_id:
            selected = (reference, document)
    result: dict[str, Any] = {"project_id": project_id, "profile": profile, "status": "reference",
                              "ready": False, "handoffs": records, "memory_files": len(memories),
                              "unsupported": len(report.unsupported),
                              "note": "本机资料查看；没有获取远端、修改源码或宣告 Agent 已加载。"}
    if handoff_id and selected is None:
        raise ValueError("所选可移植交接不存在或未通过校验。")
    if selected:
        reference, document = selected
        missing = []
        project = (config.get("projects") or {}).get(project_id)
        current_commit = None
        if not project:
            missing.append("尚未映射本机源码工作区")
        else:
            root = absolute(project)
            if not root.is_dir() or any(path.is_symlink() or getattr(path, "is_junction", lambda: False)() for path in (root, *root.parents)):
                missing.append("本机源码工作区不存在或由链接管理")
            else:
                top = repo_root(root)
                if top != root.resolve():
                    missing.append("无法核验本机源码版本（Git 不可用或非独立工作区）")
                else:
                    current_commit = _git(root, "rev-parse", "HEAD") or None
                if not reference["commit"] or current_commit != reference["commit"]:
                    missing.append("源码版本未知或与交接不一致")
                for name, expected in reference["lock_files"].items():
                    data = _file_bytes(root / name)
                    if data is None or hashlib.sha256(data).hexdigest() != expected:
                        missing.append(f"依赖锁文件缺失或不同：{name}")
        if not reference["commit"] and "源码版本未知或与交接不一致" not in missing:
            missing.append("源码版本未知或与交接不一致")
        if reference["memory_snapshot"] and not memories:
            missing.append("对应项目没有可移植记忆资料")
        missing.append("依赖安装与 Agent 新会话加载尚未核验")
        result.update(reference=reference, document=document, current_commit=current_commit, missing=missing)
    return result

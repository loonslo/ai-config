"""Desktop-only interface to the original-file migration engine."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import os
import ntpath
from pathlib import Path
import platform
from typing import Mapping

from .protocol import ApplicationProtocol, ProtocolError
from .service import ApplicationResult
from ..layout import data_root
from ..machine.backup import AGENTS, agent_roots, prepare_backup, apply_backup
from ..machine.bundle import validate_bundle
from ..machine.config import load_config
from ..machine.paths import RootMap
from ..machine.preflight import preflight, target_bytes, no_links
from ..machine.apply import plan_restore, apply_restore
from ..machine.undo import operations, prepare_undo, undo
from ..machine.verify import verify
from ..machine.guided import AGENT_LABELS
from ..machine.procs import running_apps
from ..utils import digest

PARAMS = {
    'machine_detect': set(), 'machine_history': set(),
    'machine_backup': {'destination', 'agents', 'projects'},
    'machine_restore': {'bundle', 'agents', 'root_map', 'confirm_security', 'confirm_trust', 'workbuddy_files'},
    'machine_undo': {'operation_id'},
}


class MachineProtocol(ApplicationProtocol):
    """Reuse serialized jobs and single-use previews, accepting only machine actions."""

    def __init__(self, local_path: Path, *, home: Path | None = None, environ=None, **kwargs):
        super().__init__(local_path, **kwargs)
        self.home = home or Path.home()
        self.environ = dict(os.environ if environ is None else environ)
        self.state = data_root(home=self.home, environ=self.environ) / 'state'
        self._prepared = None

    @staticmethod
    def validate_request(request):
        if not isinstance(request, Mapping):
            raise ProtocolError('E_REQUEST_INVALID', '无效请求。')
        if request.get('type') != 'preview':
            return ApplicationProtocol.validate_request(request)
        if type(request.get('protocol_version')) is not int or request.get('protocol_version') != 1 or set(request) - {'protocol_version', 'request_id', 'type', 'operation', 'params'}:
            raise ProtocolError('E_REQUEST_INVALID', '无效请求。')
        request_id = request.get('request_id')
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise ProtocolError('E_REQUEST_ID', '无效请求编号。')
        operation = request.get('operation')
        params = request.get('params', {})
        if not isinstance(operation, str) or operation not in PARAMS:
            raise ProtocolError('E_OPERATION_UNKNOWN', '此客户端只支持本地备份、恢复和撤销。')
        if not isinstance(params, dict) or set(params) - PARAMS[operation]:
            raise ProtocolError('E_PARAMS_INVALID', '无效选项。')
        required = {'machine_backup': 'destination', 'machine_restore': 'bundle', 'machine_undo': 'operation_id'}
        if operation in required and not params.get(required[operation]):
            raise ProtocolError('E_PARAMS_INVALID', '请先选择文件或保存位置。')
        for key, value in params.items():
            valid = True
            if key in {'destination', 'bundle'}:
                valid = isinstance(value, str) and Path(value).is_absolute()
            elif key == 'operation_id':
                valid = isinstance(value, str) and bool(value)
            elif key in {'confirm_security', 'confirm_trust', 'workbuddy_files'}:
                valid = isinstance(value, bool)
            elif key == 'agents':
                valid = isinstance(value, list) and bool(value) and all(isinstance(v, str) and v in AGENTS for v in value)
            elif key == 'projects':
                valid = isinstance(value, list) and all(isinstance(v, str) and Path(v).is_absolute() for v in value)
            elif key == 'root_map':
                valid = isinstance(value, list) and all(isinstance(v, dict) and set(v) == {'from', 'to'} and all(isinstance(p, str) and p for p in v.values()) for v in value)
            if not valid:
                raise ProtocolError('E_PARAMS_INVALID', '请选择有效目录、助手或恢复选项。')
        return 'preview', operation, dict(params)

    def _preview(self, request_id, operation, params, **kwargs):
        if operation == 'machine_backup':
            params = {**params, '_created': datetime.now(timezone.utc).isoformat()}
        return super()._preview(request_id, operation, params, **kwargs)

    @staticmethod
    def _can_apply(operation, params, result):
        return operation not in {'machine_detect', 'machine_history'} and result.get('can_apply') is True

    def _version(self, operation, params, result):
        config_path = data_root(home=self.home, environ=self.environ) / 'machine.config.json'
        material = {'operation': operation, 'params': params, 'data': result.data, 'detail': result.detail,
                    'config': digest(target_bytes(config_path))}
        return hashlib.sha256(json.dumps(material, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

    def _config(self, params, source_os=None):
        system = platform.system().lower()
        config = load_config(data_root(home=self.home, environ=self.environ) / 'machine.config.json',
                             home=self.home, source_os=source_os or system, target_os=system)
        if 'projects' in params:
            projects = tuple(Path(value) for value in params['projects'])
            if any(not p.is_dir() for p in projects):
                raise ValueError('工作文件夹不存在。')
            config = replace(config, core_projects=projects)
        if 'root_map' in params:
            windows_source = (source_os or system) in {'windows', 'win32', 'nt'}
            if any(not (ntpath.isabs(v['from']) if windows_source else v['from'].startswith('/'))
                   or not Path(v['to']).is_absolute() or not Path(v['to']).is_dir() for v in params['root_map']):
                raise ValueError('映射的目标必须是已经存在的绝对目录。')
            config = replace(config, root_map=RootMap(tuple((v['from'], v['to']) for v in params['root_map']), source_os or system, system))
        return config

    def _invoke(self, operation, params, *, apply, progress=None):
        if apply:
            prepared = self._prepared
            self._prepared = None
            if not prepared or prepared[0] != operation or prepared[1] != params:
                raise ProtocolError('E_PLAN_UNKNOWN', '请重新检查。')
            obj = prepared[2]
            if operation == 'machine_backup':
                return ApplicationResult(data=apply_backup(obj))
            if operation == 'machine_restore':
                report = apply_restore(obj)
                verification = verify(obj.check, restored=obj.restored)
                import uuid
                report_dir = self.state / 'machine-reports' / uuid.uuid4().hex
                no_links(report_dir)
                report_dir.mkdir(parents=True, exist_ok=False)
                for name, text in [('preflight-report.md', obj.check.markdown()),
                                   ('verify-report.md', verification.markdown()), ('todo.md', obj.check.todo())]:
                    (report_dir / name).write_text(text, encoding='utf-8')
                return ApplicationResult(data={**report, 'verification': verification.report(), 'todo': obj.check.todo(),
                                               'report_dir': str(report_dir)})
            if operation == 'machine_undo':
                return ApplicationResult(data=undo(self.state, operation_id=params['operation_id'], apply=True,
                                                  process_names=self._config({}).running_process_names))
        config = self._config(params)
        if operation == 'machine_detect':
            roots = agent_roots(self.home, config, self.environ)
            return ApplicationResult(data={'agents': [{'id': name, 'name': AGENT_LABELS[name], 'installed': root.is_dir(), 'root': str(root)} for name, root in roots.items()],
                                           'projects': [str(p) for p in config.core_projects]})
        if operation == 'machine_history':
            return ApplicationResult(data={'operations': operations(self.state)})
        selected = frozenset(params['agents']) if params.get('agents') else None
        if operation == 'machine_backup':
            obj = prepare_backup(home=self.home, config=config, out=Path(params['destination']), name='AI备份', agents=selected,
                                 environ=self.environ, now=datetime.fromisoformat(params['_created']))
            data = {**obj.preview(), 'can_apply': True}
            detail = {'entries': obj.writer.entries,
                      'sources': {str(path): (value[0], value[1]) for collection in obj.collections
                                  for path, value in collection.source_fingerprints.items()}}
        elif operation == 'machine_restore':
            bundle = Path(params['bundle'])
            manifest = validate_bundle(bundle)
            config = self._config(params, manifest['source']['os'])
            check = preflight(bundle, home=self.home, config=config, agents=selected, environ=self.environ)
            obj = plan_restore(check, state=self.state, process_names=config.running_process_names,
                               confirm_security=params.get('confirm_security', False),
                               security_hash=check.security_list_hash if params.get('confirm_security') else None,
                               codex_trust=params.get('confirm_trust', False),
                               confirm_trust=check.trust_list_hash if params.get('confirm_trust') else None,
                               workbuddy_files=params.get('workbuddy_files', False))
            data = {**check.report(), **obj.report(), 'can_apply': not check.running,
                    'source_projects': [{'id': v['project_id'], 'path': v['source_path']} for v in manifest['projects']],
                    'bundle_agents': sorted({v['agent'] for v in manifest['entries'] if v['agent'] in AGENTS})}
            detail = {'bundle': digest(bundle.read_bytes()), 'expected': {str(p): digest(target_bytes(p)) for p in obj.changes.expected},
                      'changes': {str(p): digest(b) for p, b in obj.changes.items()}}
        elif operation == 'machine_undo':
            obj = prepare_undo(self.state, operation_id=params['operation_id'])
            running = running_apps(config.running_process_names)
            data = {**undo(self.state, operation_id=params['operation_id']), 'running': running, 'can_apply': not running}
            detail = {'targets': {str(p): digest(target_bytes(p)) for p in obj[1]}, 'changes': {str(p): digest(b) for p, b in obj[1].items()}}
        else:
            raise ProtocolError('E_OPERATION_UNKNOWN', '不支持此操作。')
        self._prepared = (operation, params, obj)
        return ApplicationResult(data=data, detail=detail)

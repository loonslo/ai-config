"""Beginner restore and undo orchestration; judgments stay in core modules."""
from __future__ import annotations

from collections import Counter
from datetime import datetime,timezone
import json
import ntpath
import os
from pathlib import Path
import platform
import posixpath
from typing import Any,Callable,Mapping
import uuid
import zipfile

from sync_core.layout import data_root,default_state_path

from .apply import plan_restore,apply_restore
from .bundle import FORMAT,MAX_MANIFEST_BYTES,MAX_TOTAL_BYTES,MAX_RATIO,validate_bundle
from .collect_records import software_inventory
from .config import MachineConfig,load_config
from .guide_backup import _log_failure
from .guided import AGENT_LABELS,Cancelled,GuideIO,clean_dragged_path,desktop_path,local_time
from .paths import RootMap
from .preflight import preflight,no_links
from .procs import process_names
from .undo import operations,prepare_undo,undo
from .verify import verify


def removable_roots() -> list[Path]:
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.GetDriveTypeW.argtypes=[ctypes.c_wchar_p]
        bits=kernel.GetLogicalDrives()
        return [Path(f'{chr(65+index)}:/') for index in range(26)
                if bits & (1<<index) and kernel.GetDriveTypeW(f'{chr(65+index)}:\\')==2]
    root=Path('/Volumes')
    return [path for path in root.iterdir() if path.is_dir() and not path.is_symlink()] if root.is_dir() else []


def backup_files(roots: list[Path]) -> list[dict[str,Any]]:
    """Peek only at bounded manifest data in top-level ZIPs during discovery."""
    found={}
    for root in roots:
        if not root.is_dir() or root.is_symlink():
            continue
        try:
            no_links(root)
        except ValueError:
            continue
        for path in root.glob('*.zip'):
            if not path.is_file() or path.is_symlink() or path.stat().st_size>MAX_TOTAL_BYTES:
                continue
            try:
                with zipfile.ZipFile(path) as archive:
                    info=archive.getinfo('manifest.json')
                    if (info.file_size>MAX_MANIFEST_BYTES or info.compress_type not in {zipfile.ZIP_STORED,zipfile.ZIP_DEFLATED}
                            or info.file_size and (not info.compress_size or info.file_size/info.compress_size>MAX_RATIO)):
                        continue
                    with archive.open(info) as handle:
                        raw=handle.read(MAX_MANIFEST_BYTES+1)
                    if len(raw)>MAX_MANIFEST_BYTES:
                        continue
                    manifest=json.loads(raw)
                    if manifest.get('format')!=FORMAT:
                        continue
                    when=datetime.fromisoformat(manifest['created_at'].replace('Z','+00:00'))
                    if when.tzinfo is None:
                        when=when.replace(tzinfo=timezone.utc)
                    found[str(path.resolve())]={'path':path,'created_at':when,'bytes':path.stat().st_size}
            except (OSError,ValueError,KeyError,TypeError,zipfile.BadZipFile,RuntimeError):
                continue
    return sorted(found.values(),key=lambda item:item['created_at'],reverse=True)


def _yes(answer: str) -> bool:
    return answer.casefold() in {'y','yes','是'}


def guide_restore(bundle: Path | None=None, *, io: GuideIO | None=None, home: Path | None=None,
                  config: MachineConfig | None=None, environ: Mapping[str,str] | None=None,
                  os_name: str | None=None, root_map: RootMap | None=None,
                  desktop: Callable[[Path],Path]=desktop_path, drives: Callable[[],list[Path]]=removable_roots,
                  launcher: Path | None=None, processes: Callable[[],list[str]]=process_names,
                  software: dict[str,Any] | None=None) -> int:
    ui=io or GuideIO()
    user_home=home or Path.home()
    env=os.environ if environ is None else environ
    system=os_name or platform.system().lower()
    completed=False
    saved=None
    try:
        ui.ask('从备份文件恢复 AI 助手。原有不同内容会保留，并另存备份版本供你对照。按回车继续；q 退出。')
        state=default_state_path(home=user_home,environ=dict(env))
        selected_config=config or load_config(data_root(home=user_home,environ=dict(env))/'machine.config.json',home=user_home,target_os=system)
        history=operations(state)
        if history:
            answer=ui.ask('1 从备份文件恢复（默认）；2 撤销上一次恢复。输入编号，或按回车继续。')
            if answer=='2':
                for index,item in enumerate(history,1):
                    when=datetime.fromisoformat(item['created_at'].replace('Z','+00:00'))
                    ui.say(f'{index}. {local_time(when)}，涉及 {item["change_count"]} 个文件。')
                while True:
                    answer=ui.ask('选择要撤销的一次恢复（回车选择第 1 次；q 退出）。')
                    if not answer or answer.isdigit() and 1<=int(answer)<=len(history):
                        break
                    ui.say('请输入上面显示的编号。')
                operation=history[int(answer or '1')-1]
                _,plan,_=prepare_undo(state,operation_id=operation['operation_id'])
                for target in plan:
                    ui.data(str(target))
                answer=ui.ask(f'将把 {len(plan)} 个文件恢复到之前的状态。开始撤销吗？（回车开始；q 退出）')
                if answer and not _yes(answer):
                    raise Cancelled
                undo(state,operation_id=operation['operation_id'],apply=True,
                     process_names=selected_config.running_process_names,processes=processes())
                completed=True
                ui.say('已撤销这次恢复。原有文件已还原；需要时可以再次从备份文件恢复。')
                ui.finish()
                return 0
        if bundle is None:
            folder=launcher or Path(__file__).resolve().parents[2]
            candidates=backup_files([desktop(user_home),user_home/'Downloads',folder,folder.parent,*drives()])
            if len(candidates)==1:
                bundle=candidates[0]['path']
            elif candidates:
                for index,item in enumerate(candidates,1):
                    ui.say(f'{index}. {local_time(item["created_at"])}，{item["bytes"]/1024:.1f} KB')
                    ui.data(str(item['path']))
                while True:
                    answer=ui.ask('选择备份文件（回车选择第 1 个；q 退出）。')
                    if not answer or answer.isdigit() and 1<=int(answer)<=len(candidates):
                        bundle=candidates[int(answer or '1')-1]['path']
                        break
                    ui.say('请输入上面显示的编号。')
            else:
                bundle=clean_dragged_path(ui.ask('没有找到备份文件。请把备份文件拖进这个窗口，然后按回车；q 退出。'))
        no_links(bundle)
        try:
            manifest=validate_bundle(bundle)
        except (OSError,ValueError):
            ui.say('这个文件不完整或不是备份文件。原有数据均保留；请重新取得完整备份再试。')
            ui.finish(code='E7421')
            return 1
        names=[name for name in AGENT_LABELS if any(entry.get('agent')==name for entry in manifest['entries'])]
        if not names:
            raise ValueError('backup has no supported assistant')
        indices=ui.choose('选择要恢复的 AI 助手',[AGENT_LABELS[name] for name in names])
        agents=frozenset(names[index] for index in indices)
        if not agents:
            raise Cancelled
        mapper=root_map or RootMap(selected_config.root_map.rules,manifest['source']['os'],system)
        versions=software if software is not None else software_inventory(home=user_home)
        def check_now():
            return preflight(bundle,home=user_home,config=selected_config,agents=agents,environ=env,os_name=system,
                             root_map=mapper,processes=processes(),software=versions)
        check=check_now()
        if check.projects and not any(check.projects.values()):
            ui.say('备份里的工作文件夹在这台电脑上找不到。')
            answer=ui.ask('工作文件夹现在在哪？把文件夹拖进窗口后按回车；直接回车跳过这些文件夹；q 退出。')
            if answer:
                destination=clean_dragged_path(answer)
                if not destination.is_dir():
                    raise ValueError('mapping target missing')
                paths=[record['source_path'] for record in manifest['projects']]
                common=(ntpath.commonpath(paths) if manifest['source']['os']=='windows' else posixpath.commonpath(paths))
                mapper=RootMap(((common,str(destination)),),manifest['source']['os'],system)
                check=check_now()
        while check.running:
            ui.say('请关闭正在运行的程序：'+'、'.join(check.running))
            ui.ask('关闭后按回车重新检查；q 退出。')
            check=check_now()
        created=datetime.fromisoformat(manifest['created_at'].replace('Z','+00:00'))
        label='Windows' if manifest['source']['os']=='windows' else 'Mac' if manifest['source']['os'] in {'darwin','macos'} else '其他系统'
        ui.say(f'备份于 {local_time(created)}，来自 {label} 电脑。')
        counts=Counter(item.status for item in check.items)
        ui.say(f'可以新增 {counts["new"]} 项；已有不同内容 {counts["differs"]} 项，会保留现有并另存备份版本。')
        ui.say(f'找不到的工作文件夹 {sum(path is None for path in check.projects.values())} 个，相关内容已跳过。')
        confirm_security=False;shown_security=None
        if check.security_list:
            ui.say('以下设置涉及模型选择或安全权限，默认不恢复。')
            labels={'model':'模型','service_tier':'服务等级','approval_policy':'操作批准方式','sandbox_mode':'运行限制',
                    'skipDangerousModePermissionPrompt':'危险操作提醒'}
            for item in check.security_list:
                ui.say(AGENT_LABELS[item['agent']]+'：'+labels[item['field']])
                ui.data(json.dumps(item['value'],ensure_ascii=False))
            shown_security=check.security_list_hash
            confirm_security=_yes(ui.ask('恢复这些设置吗？（回车不恢复；输入 y 同意；q 退出）'))
        trust=False;shown_trust=None
        if check.trust_list:
            ui.say('将信任以下文件夹：Codex 会加载其中的配置、运行钩子和规则。默认不恢复。')
            for item in check.trust_list:
                ui.data(item['path'])
            shown_trust=check.trust_list_hash
            trust=_yes(ui.ask('信任这些文件夹吗？（回车不恢复；输入 y 同意；q 退出）'))
        workbuddy=False
        if any(item.entry['agent'].startswith('workbuddy') for item in check.items):
            ui.say('WorkBuddy 的人设、记忆与技能只有文本候选，写回后仍需你打开助手核对。')
            workbuddy=_yes(ui.ask('复制这些文本候选吗？（回车跳过；输入 y 同意；q 退出）'))
        plan=plan_restore(check,state=state,process_names=selected_config.running_process_names,
                          confirm_security=confirm_security,security_hash=shown_security if confirm_security else None,
                          codex_trust=trust,confirm_trust=shown_trust if trust else None,workbuddy_files=workbuddy)
        answer=ui.ask(f'将新建或补充 {len(plan.changes)} 个文件，跳过 {len(plan.skipped)} 项，原有不同内容会保留。开始恢复吗？（回车开始；q 退出）')
        if answer and not _yes(answer):
            raise Cancelled
        report=apply_restore(plan,processes=processes())
        completed=True
        saved=report['backup']
        verification=verify(check,restored=plan.restored,software=versions)
        report_dir=state/'machine-reports'/uuid.uuid4().hex
        no_links(report_dir)
        report_dir.mkdir(parents=True,exist_ok=False)
        for name,text in (('preflight-report.md',check.markdown()),('todo.md',check.todo()),('verify-report.md',verification.markdown())):
            (report_dir/name).write_text(text,encoding='utf-8')
        attention=sum(item['status'] in {'FAIL','MANUAL'} for item in verification.checks)
        ui.say(f'恢复已完成；有 {attention} 项需要你看一下。原有不同内容均保留。' if attention else '恢复与文件核对全部正常，原有不同内容均保留。')
        for item in plan.conflicts:
            if item.get('saved_as'):
                ui.say('现有版本已保留，请对照以下另存版本：')
                ui.data(item['saved_as'])
        for warning in plan.warnings:
            ui.say(warning)
        ui.say('接下来：重新登录并授权；按清单重装第三方技能与插件；在新会话里确认规则和记忆已生效。')
        ui.say('觉得不对，可再次运行「恢复」选择撤销。详细说明保存在：')
        ui.data(str(report_dir))
        answer=ui.ask('按回车结束；输入 d 查看详细信息。')
        if answer.casefold()=='d':
            ui.data(verification.markdown())
            ui.finish()
        return 1 if verification.exit_code else 0
    except Cancelled:
        ui.say('已退出。恢复已经完成，原有版本的备份保留；可再次运行「恢复」选择撤销。' if completed else '已退出，没有改动任何文件。需要时可重新打开恢复。')
        ui.finish()
        return 0
    except Exception as error:
        log=_log_failure(error,home=user_home,env=env)
        ui.say('本次恢复或核对没有全部完成。')
        ui.say('原有数据：写入前的备份保留；发生冲突时现有内容保留。')
        ui.say('下一步：关闭助手，核对说明；已经恢复的内容可再次运行「恢复」选择撤销。')
        if saved:
            ui.data(str(saved))
        if log:
            ui.say('可以把以下日志位置提供给技术支持：')
            ui.data(str(log))
        ui.finish(code='E7420')
        return 1

"""File/field verification plus explicit manual loading and login checks."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import random
from typing import Any
import tomllib

from sync_core.utils import digest
from sync_core.streaming import file_digest

from .preflight import Preflight, get_field, target_bytes, fields_parent
from .paths import norm
from .guided import AGENT_LABELS,KIND_LABELS,RESTORE_REASON_LABELS
from .privacy import personal_text,private_text,public_value


STATUS_WORDS={'PASS':'一致','FAIL':'核验失败','MANUAL':'需要人工确认','SKIP':'已跳过',
              'KEPT':'保留本机内容','PARTIAL':'部分字段已核验','SAVED':'仅另存副本一致'}


def verification_groups(checks: list[dict[str,Any]]) -> list[dict[str,Any]]:
    groups={}
    for index,item in enumerate(checks):
        agent=item.get('agent')
        kind='not_selected' if item.get('reason')=='agent_not_selected' else item.get('kind','followup')
        key=(agent,kind)
        if key not in groups:
            label=(AGENT_LABELS[agent] if kind=='not_selected' else
                   AGENT_LABELS[agent]+' '+KIND_LABELS[kind] if agent else '环境与加载确认')
            groups[key]={'label':label,'agent':agent,'kind':kind,'counts':{},'check_indexes':[]}
        group=groups[key]
        group['check_indexes'].append(index)
        counts=group['counts']
        counts[item['status']]=counts.get(item['status'],0)+1
    return list(groups.values())


def rule_questions(check: Preflight, *, verified_ids: set[str] | None = None) -> list[dict[str,str]]:
    questions=[]
    for item in check.items:
        if item.entry['kind']!='rules' or item.reason or (verified_ids is not None and item.entry['id'] not in verified_ids):
            continue
        lines=[]
        in_comment=False
        fence=None
        for raw in item.data.decode('utf-8').splitlines():
            line=raw.strip()
            if in_comment or '<!--' in line:
                in_comment='-->' not in line
                continue
            if line.startswith(('```','~~~')):
                marker=line[:3]
                fence=None if fence==marker else marker if fence is None else fence
                continue
            if line and fence is None:
                lines.append(line)
        counts=Counter(lines)
        candidates=[line for line in lines if counts[line]==1 and len(line)>=12 and not line.startswith(('#','```'))
                    and not personal_text(line) and not private_text(line)]
        if candidates:
            sentence=random.SystemRandom().choice(candidates)
            questions.append({'agent':item.entry['agent'],'prompt':f'请复述你全局规则里以「{sentence[:12]}」开头的那一整行。',
                              'expected':sentence})
    return questions


@dataclass
class Verification:
    checks: list[dict[str,Any]]
    questions: list[dict[str,str]]

    @property
    def exit_code(self) -> int:
        return 4 if any(item['status']=='FAIL' for item in self.checks) else 0

    def report(self) -> dict[str,Any]:
        return {'checks':self.checks,'counts':dict(Counter(item['status'] for item in self.checks)),
                'groups':verification_groups(self.checks),
                'questions':self.questions,'exit_code':self.exit_code}

    def markdown(self) -> str:
        lines=['# 恢复核对结果','']
        for group in verification_groups(self.checks):
            summary='本次未选择' if group['kind']=='not_selected' else '；'.join(
                f'{count} 项{STATUS_WORDS[status]}' for status,count in group['counts'].items())
            lines.append(f"## {group['label']}：{summary}")
            lines.append('')
            for index in group['check_indexes']:
                item=self.checks[index]
                identity=item.get('target') or item.get('project') or item.get('logical_path') or item['label']
                lines.append(f"- {identity}：{STATUS_WORDS[item['status']]}")
                if item.get('reason'):
                    lines.append('  原因：'+RESTORE_REASON_LABELS.get(item['reason'],'需要人工核对'))
                for field in ('verified_fields','retained_fields','skipped_fields'):
                    if item.get(field):
                        title={'verified_fields':'已核验字段','retained_fields':'保留本机字段','skipped_fields':'跳过字段'}[field]
                        lines.append('  '+title+'：'+', '.join(item[field]))
            lines.append('')
        lines += ['', '## 新会话确认规则', '', '在对应助手的新会话里提问，再与你的原句对照。文件一致不代表助手已经读取。']
        for item in self.questions:
            lines += ['',AGENT_LABELS[item['agent']]+'：',item['prompt'],'对照原句：'+item['expected']]
        return public_value('\n'.join(lines)+'\n')


def verify(check: Preflight, *, restored: list[dict[str,Any]] | None = None,
           skipped: list[dict[str,Any]] | None = None, conflicts: list[dict[str,Any]] | None = None,
           software: dict[str,Any] | None = None, reinstall_done: bool=False) -> Verification:
    by_id={record['entry_id']:record for record in restored} if restored is not None else None
    skipped_by_id=defaultdict(list)
    retained_by_id=defaultdict(list)
    for value in skipped or []:
        skipped_by_id[value['entry_id']].append(value)
    for value in conflicts or []:
        if value.get('field') and value['reason']=='field_differs' and value.get('decision')!='overwrite':
            retained_by_id[value['entry_id']].append(value['field'])
    results=[]
    for item in check.items:
        entry=item.entry
        label=AGENT_LABELS[entry['agent']]+' '+KIND_LABELS[entry['kind']]
        record=by_id.get(entry['id']) if by_id is not None else None
        target=item.target
        status='PASS'
        skipped_items=skipped_by_id[entry['id']]
        retained_fields=retained_by_id[entry['id']]
        skipped_fields=[value['field'] for value in skipped_items if value.get('field') and value['reason']!='kept_local']
        reason=item.reason or (skipped_items[0]['reason'] if skipped_items else '')
        if reason=='kept_local' and entry['kind']=='settings_fields' and record is None:
            skipped_fields=[key for key in item.fields if key not in retained_fields]
        if item.reason:
            status='MANUAL' if item.reason=='manual_trust' else 'SKIP'
        elif by_id is not None and record is None:
            status='KEPT' if reason=='kept_local' else 'SKIP' if reason else 'MANUAL'
        else:
            try:
                if record is not None and record.get('target'):
                    target=Path(record['target'])
                current=target_bytes(target) if target else None
                if entry['kind']=='settings_fields':
                    fields=record['fields'] if record is not None else {key:value for key,value in item.fields.items() if key not in item.confirm}
                    raw=json.loads(current) if current and target.suffix == '.json' else tomllib.loads(current.decode('utf-8')) if current else {}
                    if item.field_path:
                        raw=fields_parent(raw,item.field_path)
                    if any(not get_field(raw,key)[0] or get_field(raw,key)[1]!=value for key,value in fields.items()):
                        status='FAIL'
                    if not fields:
                        status='MANUAL'
                    elif status=='PASS' and (retained_fields or skipped_fields):
                        status='PARTIAL'
                elif entry['kind']=='trust_fields':
                    raw=tomllib.loads(current.decode('utf-8')) if current else {}
                    path=record['trust_path'] if record is not None else item.fields['path']
                    tables=raw.get('projects',{})
                    table=next((value for key,value in tables.items() if norm(key,check.target_os).casefold()==path.casefold()),{}) if check.target_os in {'windows','nt','win32'} else tables.get(path,{})
                    if table.get('trust_level')!=(record['trust_level'] if record is not None else item.fields['trust_level']):
                        status='FAIL'
                elif digest(current)!=entry['sha256']:
                    status='FAIL'
                elif target!=item.target:
                    status='SAVED'
            except (OSError,ValueError,TypeError,KeyError):
                status='FAIL'
        if record and record.get('exported'):
            status = 'MANUAL' if target and digest(target_bytes(target)) == record['sha256'] else 'FAIL'
            reason = 'exported'
        if status in {'PASS', 'SAVED', 'PARTIAL'} and any(flag.startswith('redacted:') for flag in entry.get('flags', [])):
            status, reason = 'MANUAL', 'redacted'
        results.append({'entry_id':entry['id'],'agent':entry['agent'],'kind':entry['kind'],
                        'logical_path':entry['logical_path'],'label':label,'status':status,'reason':reason,
                        'target':str(target) if target else None,
                        'project':str(check.projects.get(entry.get('project_id')) or ''),
                        'verified_fields':list(record.get('fields',{})) if record else [],
                        'retained_fields':retained_fields,'skipped_fields':skipped_fields})
    for entry in check.manifest['entries']:
        if entry.get('agent') in AGENT_LABELS and entry['agent'] not in check.agents and entry['agent'] != 'system':
            results.append({'entry_id':entry['id'],'agent':entry['agent'],'kind':entry['kind'],
                            'logical_path':entry['logical_path'],
                            'label':AGENT_LABELS[entry['agent']]+' '+KIND_LABELS[entry['kind']],
                            'status':'SKIP','reason':'agent_not_selected','target':None})
    for record in restored or []:
        if record.get('kind')!='history_files':
            continue
        try:
            status='PASS' if file_digest(Path(record['target']))==record['sha256'] else 'FAIL'
            if status=='PASS' and (record.get('history_unmapped') or record.get('saved_as')):
                status='SAVED'
            if status in {'PASS','SAVED'} and record.get('redacted'):
                status='MANUAL'
        except (OSError,ValueError):
            status='FAIL'
        results.append({**record,'label':AGENT_LABELS[record['agent']]+' 历史记录','status':status,
                        'reason':'redacted' if record.get('redacted') else 'history_unmapped' if record.get('history_unmapped') else ''})
    for record in skipped or []:
        if record.get('kind')=='history_files':
            results.append({**record,'label':AGENT_LABELS[record['agent']]+' 历史记录','status':'SKIP'})
    prior=json.loads(check.files.get('reports/software.json',b'{}')).get('versions',{})
    if software is None:
        results.append({'label':'软件版本','status':'MANUAL'})
    else:
        for name,value in prior.items():
            if not value:
                continue
            actual=software.get('versions',{}).get(name)
            status='PASS' if actual and str(value).lstrip('v').split('.')[0]==str(actual).lstrip('v').split('.')[0] else 'FAIL'
            results.append({'label':'软件版本 '+name,'status':status})
    results.extend([{'label':'第三方技能与插件重装清单','status':'PASS' if reinstall_done else 'MANUAL'},
                    {'label':'重新登录与授权','status':'MANUAL'},{'label':'助手实际读取规则与记忆','status':'MANUAL'}])
    verified_ids={item['entry_id'] for item in results if item.get('entry_id') and item['status']=='PASS'}
    return Verification(results,rule_questions(check,verified_ids=verified_ids))

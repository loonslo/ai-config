"""File/field verification plus explicit manual loading and login checks."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import json
import random
import re
from typing import Any
import tomllib

from sync_core.utils import digest

from .preflight import Preflight, get_field, target_bytes
from .paths import norm
from .guided import AGENT_LABELS,KIND_LABELS


def rule_questions(check: Preflight) -> list[dict[str,str]]:
    questions=[]
    for item in check.items:
        if item.entry['kind']!='rules':
            continue
        lines=[line.strip() for line in item.data.decode('utf-8').splitlines() if line.strip()]
        counts=Counter(lines)
        candidates=[line for line in lines if counts[line]==1 and len(line)>=12 and not line.startswith(('#','```'))
                    and not re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',line)]
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
                'questions':self.questions,'exit_code':self.exit_code}

    def markdown(self) -> str:
        words={'PASS':'一致','FAIL':'需要检查','MANUAL':'需要你确认','SKIP':'本次未检查'}
        lines=['# 恢复核对结果','']
        for item in self.checks:
            lines.append(f"- {item['label']}：{words[item['status']]}。")
            if item.get('target'):
                lines.append('  '+item['target'])
        lines += ['', '## 新会话确认规则', '', '在对应助手的新会话里提问，再与你的原句对照。文件一致不代表助手已经读取。']
        for item in self.questions:
            lines += ['',AGENT_LABELS[item['agent']]+'：',item['prompt'],'对照原句：'+item['expected']]
        return '\n'.join(lines)+'\n'


def verify(check: Preflight, *, restored: list[dict[str,Any]] | None = None,
           software: dict[str,Any] | None = None, reinstall_done: bool=False) -> Verification:
    by_id={record['entry_id']:record for record in restored} if restored is not None else None
    results=[]
    for item in check.items:
        entry=item.entry
        label=AGENT_LABELS[entry['agent']]+' '+KIND_LABELS[entry['kind']]
        record=by_id.get(entry['id']) if by_id is not None else None
        target=item.target
        status='PASS'
        if item.reason:
            status='MANUAL' if item.reason=='manual_trust' else 'SKIP'
        elif by_id is not None and record is None:
            status='MANUAL'
        else:
            try:
                if record is not None and record.get('target'):
                    from pathlib import Path
                    target=Path(record['target'])
                current=target_bytes(target) if target else None
                if entry['kind']=='settings_fields':
                    fields=record['fields'] if record is not None else {key:value for key,value in item.fields.items() if key not in item.confirm}
                    raw=json.loads(current) if current and entry['agent']=='claude' else tomllib.loads(current.decode('utf-8')) if current else {}
                    if any(not get_field(raw,key)[0] or get_field(raw,key)[1]!=value for key,value in fields.items()):
                        status='FAIL'
                    if not fields:
                        status='MANUAL'
                elif entry['kind']=='trust_fields':
                    raw=tomllib.loads(current.decode('utf-8')) if current else {}
                    path=record['trust_path'] if record is not None else item.fields['path']
                    tables=raw.get('projects',{})
                    table=next((value for key,value in tables.items() if norm(key,check.target_os).casefold()==path.casefold()),{}) if check.target_os in {'windows','nt','win32'} else tables.get(path,{})
                    if table.get('trust_level')!=(record['trust_level'] if record is not None else item.fields['trust_level']):
                        status='FAIL'
                elif digest(current)!=entry['sha256']:
                    status='FAIL'
            except (OSError,ValueError,TypeError,KeyError):
                status='FAIL'
        results.append({'entry_id':entry['id'],'label':label,'status':status,'target':str(target) if target else None})
    for entry in check.manifest['entries']:
        if entry.get('agent') in AGENT_LABELS and entry['agent'] not in check.agents:
            results.append({'entry_id':entry['id'],'label':AGENT_LABELS[entry['agent']]+' '+KIND_LABELS[entry['kind']],
                            'status':'SKIP','target':None})
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
    return Verification(results,rule_questions(check))

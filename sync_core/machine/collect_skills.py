"""Carry each skill copy separately with source evidence and artifact exclusions."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
from typing import Callable

from .bundle import BundleError, BundleWriter, MAX_FILE_BYTES
from .collect_classified import read_source
from .collect_tier1 import CollectionResult, project_id
from .collect_projects import _owner, _key
from .collect_workbuddy import _project_roots
from .config import MachineConfig, excluded_path
from .coverage import no_links, is_link, safe_name
from .provenance import ProvenanceHints, resolve_skill
from .skills_links import link_target


_ARTIFACT_DIRS = {'.git','node_modules','__pycache__','.venv'}
_GIT_FILES = {'.git', '.gitconfig', '.git-credentials', '.gitignore', '.gitattributes', '.gitmodules'}
_PROGRAM = {'.exe','.dll','.so','.dylib','.node','.pyd'}


@dataclass
class SkillsResult(CollectionResult):
    skills: list[dict] = field(default_factory=list)
    checks: list[Callable[[], bool]] = field(default_factory=list, repr=False)

    def verify_sources_unchanged(self) -> bool:
        try:
            return super().verify_sources_unchanged() and all(check() for check in self.checks)
        except (OSError, ValueError):
            return False


def _size(path: Path) -> int | None:
    failed = False
    def onerror(_):
        nonlocal failed
        failed = True
    try:
        if path.is_file():
            return path.stat().st_size
        total = 0
        for folder, directories, files in os.walk(path,followlinks=False,onerror=onerror):
            directories[:] = [n for n in directories if n.casefold() != '.git' and not is_link(Path(folder)/n)]
            for name in files:
                if name.casefold() in _GIT_FILES:
                    continue
                child = Path(folder)/name
                if not is_link(child):
                    total += child.stat().st_size
        return None if failed else total
    except OSError:
        return None


def collect_skills(writer: BundleWriter, *, home: Path, config: MachineConfig, roots: dict[str,Path],
                   agents: frozenset[str], os_name: str, max_file_bytes: int = MAX_FILE_BYTES) -> SkillsResult:
    result = SkillsResult()
    # (agent, skill container, restore root, physical boundary, project, holder, via)
    containers = []
    def excluded(path: Path, boundary: Path) -> bool:
        return excluded_path(path,config=config,home=home,os_name=os_name,boundary=boundary)
    for agent in sorted(agents):
        root = roots[agent]
        if not root.is_dir() or not no_links(root) or excluded(root,root):
            continue
        container = root/'skills'
        via = 'direct'
        if agent == 'claude':
            try:
                container, linked = link_target(home,root)
                if linked:
                    via = 'approved-link'
                    result.approved_links[root/'skills'] = container
                    result.checks.append(lambda r=root,c=container: link_target(home,r)==(c,True))
            except (OSError,BundleError):
                result.warnings.append({'code':'E7501','message':'一个技能链接不符合允许范围，已跳过；原文件保留，请核对技能目录。'})
                continue
        holder = {'claude':'claude-global','codex':'codex-global','shared':'agents-shared'}.get(agent,agent)
        containers.append((agent,container,root,container if via=='approved-link' else root,None,holder,via))
    for project in config.core_projects:
        if not project.is_dir() or not no_links(project) or excluded(project,project):
            continue
        for agent, branch in [('claude','.claude'),('codex','.codex'),('shared','.agents')]:
            if agent in agents or agent=='shared' and 'codex' in agents:
                # Project .agents belongs to the project, restored by the Codex selector.
                actual = 'codex' if agent=='shared' else agent
                holder = 'claude-project' if actual=='claude' else 'codex-global'
                containers.append((actual,project/branch/'skills',project,project,project,holder,'direct'))
        for agent in ('workbuddy','workbuddy-ai'):
            if agent in agents:
                for folder in _project_roots(project,agent,excluded=lambda p:excluded(p,project)):
                    containers.append((agent,folder/'skills',project,project,project,'workbuddy-project','direct'))
    for agent, container, restore_root, boundary, project, holder, via in containers:
        if project is not None and _owner(str(container), config.core_projects, os_name) != _key(project, os_name):
            continue
        if not container.is_dir() or not no_links(container) or excluded(container,boundary):
            continue
        lock = None
        lock_source = container.parent/'.skill-lock.json'
        if (agent=='shared' or container == home/'.agents/skills') and lock_source.is_file():
            raw = read_source(lock_source,boundary if lock_source.is_relative_to(boundary) else container.parent,result)
            try:
                parsed = json.loads(raw) if raw is not None else None
                lock = parsed.get('skills') if isinstance(parsed,dict) and isinstance(parsed.get('skills'),dict) else None
                if lock is not None and project is None and agent=='shared' and writer.wants('skills','skills_third'):
                    clean, flags = writer.prepare_content(raw,logical_path='shared:main/.skill-lock.json',rule_id='AG-02',format_hint='.json')
                    if clean is not None:
                        writer.add_file('files/shared/main/.skill-lock.json',clean,agent='shared',instance='main',kind='skills',logical_path='shared:main/.skill-lock.json',
                                        rule_id='AG-02',nature='C',group='skills_third',flags=flags)
            except (ValueError,UnicodeError):
                result.warnings.append({'code':'E7102','message':'一个技能来源锁文件无法解析，已按来源不明处理。'})
        try:
            directories = [p for p in sorted(container.iterdir()) if p.name.casefold() != '.git' and p.is_dir() and no_links(p)]
        except OSError:
            logical = f'project:{project_id(project,os_name)}/{container.relative_to(project).as_posix()}' if project else f'{agent}:main/skills'
            result.exclusions.append({'logical_path':logical,'reason':'enumeration_failed'})
            result.warnings.append({'code':'E7101','message':'一个技能目录无法枚举，已跳过，请核对排除清单。'})
            continue
        sibling_hints = {}
        for skill in directories:
            if skill.name == '.system' and agent == 'codex':
                for vendor in sorted(skill.iterdir()):
                    if vendor.is_dir() and no_links(vendor):
                        result.skills.append(_record(vendor.name,holder,via,resolve_skill(vendor,hints=ProvenanceHints(vendor_system=True))))
                continue
            if excluded(skill,boundary):
                continue
            hints = ProvenanceHints(lock=lock,siblings=sibling_hints)
            origin = resolve_skill(skill,hints=hints)
            result.coverage_origins[skill] = origin['origin']
            result.checks.append(lambda s=skill,h=hints,o=origin: resolve_skill(s,hints=h)==o)
            record = _record(skill.name,holder,via,origin)
            record['id'] = f's{len(result.skills)+1:04d}'
            result.skills.append(record)
            if not writer.wants('skills','skills_third' if origin['origin']=='third_party' else 'skills_own'):
                continue
            evidence = skill/'package.json'
            if origin['source']['evidence']=='package.json':
                read_source(evidence,boundary,result)
            hashes = []; flags_seen=[]; partial=False
            pid = project_id(project,os_name) if project else None
            def enumeration_failed(error):
                nonlocal partial
                partial = True
                path = Path(error.filename) if error.filename else skill
                relative = path.relative_to(skill).as_posix() if path.is_relative_to(skill) and path != skill else '<技能目录>'
                logical_relative = path.relative_to(project).as_posix() if project and path.is_relative_to(project) else 'skills/'+skill.name+'/'+relative
                record['excluded'].append({'path':safe_name(relative),'reason':'enumeration_failed','size':None})
                result.exclusions.append({'logical_path':f'project:{pid}/{logical_relative}' if pid else f'{agent}:main/{logical_relative}',
                                          'reason':'enumeration_failed'})
            for folder, dirs, files in os.walk(skill,followlinks=False,onerror=enumeration_failed):
                parent = Path(folder)
                kept=[]
                for name in dirs:
                    path = parent/name
                    if name.casefold() == '.git':
                        record['excluded'].append({'path':safe_name(path.relative_to(skill).as_posix()),'reason':'git_metadata_excluded','size':None})
                        continue
                    if is_link(path) or excluded(path,boundary):
                        continue
                    if name in _ARTIFACT_DIRS:
                        record['excluded'].append({'path':safe_name(path.relative_to(skill).as_posix()),'reason':'build_artifact','size':_size(path)})
                    else:
                        kept.append(name)
                dirs[:]=kept
                for name in sorted(files):
                    source = parent/name
                    if name.casefold() in _GIT_FILES:
                        record['excluded'].append({'path':safe_name(source.relative_to(skill).as_posix()),'reason':'git_metadata_excluded','size':None})
                        continue
                    if not no_links(source) or excluded(source,boundary):
                        continue
                    relative = source.relative_to(skill).as_posix()
                    logical_relative = source.relative_to(project).as_posix() if project else 'skills/'+skill.name+'/'+relative
                    logical = f'project:{pid}/{logical_relative}' if pid else f'{agent}:main/{logical_relative}'
                    result.coverage_logical[source] = logical
                    try:
                        size = source.stat().st_size
                    except OSError:
                        partial = True
                        record['excluded'].append({'path':safe_name(relative),'reason':'metadata_unreadable','size':None})
                        result.exclusions.append({'logical_path':logical,'reason':'metadata_unreadable'})
                        continue
                    archive = f'files/projects/{pid}/{agent}/{logical_relative}' if pid else f'files/{agent}/{agent if agent.startswith("workbuddy") else "main"}/{logical_relative}'
                    reason = ('build_artifact' if name.endswith('_migration.json') or source.suffix.lower()=='.pyc' or
                              origin['origin']=='third_party' and source.suffix.lower() in _PROGRAM else 'too_large' if size>max_file_bytes else '')
                    if not reason and len(archive) > 240:
                        reason = 'path_too_long'
                        writer.oversize.append({'logical_path': logical, 'size': size, 'reason': reason})
                    if reason:
                        record['excluded'].append({'path':safe_name(relative),'reason':reason,'size':size})
                        result.exclusions.append({'logical_path':logical,'reason':reason,'size':size})
                        continue
                    data = read_source(source,boundary,result)
                    if data is None:
                        partial=True
                        record['excluded'].append({'path':safe_name(relative),'reason':'unreadable','size':size})
                        result.exclusions.append({'logical_path':logical,'reason':'unreadable','size':size})
                        continue
                    data, flags = writer.prepare_content(data,logical_path=logical,rule_id='SK-02' if origin['origin']=='third_party' else 'SK-01',
                                                         origin=origin['origin'],confidence=origin['source']['confidence'],format_hint=source.suffix,
                                                         allow_secret=source in config.allow_secret_hit_paths)
                    if data is None:
                        partial=True
                        result.exclusions.append({'logical_path':logical,'reason':'secret_hit' if writer.flagged_policy=='skip' else 'skipped_by_policy'})
                        continue
                    if writer.add_file(archive,data,agent=agent,instance=agent if agent.startswith('workbuddy') else 'main',kind='skills',logical_path=logical,
                                       project_id=pid,restore='manual' if agent.startswith('workbuddy') else 'auto',flags=flags,
                                       rule_id='SK-02' if origin['origin']=='third_party' else 'SK-01',nature='C' if origin['origin']=='third_party' else 'A',
                                       group='skills_third' if origin['origin']=='third_party' else 'skills_own',holder=holder,provenance_id=record['id'],
                                       conflict_group='skill:'+skill.name,redactions=sum(int(f.split(':')[1]) for f in flags if f.startswith('redacted:'))):
                        digest=hashlib.sha256(data).hexdigest();hashes.append((relative,digest))
                        record['files']+=1;record['bytes']+=len(data);flags_seen.extend(flags)
                        if relative=='SKILL.md':record['skill_md_sha256']=digest
                    else:
                        partial=True
                        record['excluded'].append({'path':safe_name(relative),'reason':'path_too_long','size':size})
            record['content_sha256']=hashlib.sha256(json.dumps(sorted(hashes),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            actionable_excluded = [e for e in record['excluded'] if e['reason'] != 'git_metadata_excluded']
            partial = partial or any(f.startswith('redacted:') for f in flags_seen) or any(e['reason']!='build_artifact' for e in actionable_excluded)
            record['carried']='partial' if partial else 'verbatim_without_artifacts' if record['excluded'] else 'verbatim'
            if actionable_excluded:
                hint = ('按来源说明重新安装或构建缺少的程序文件。' if all(e['reason']=='build_artifact' for e in actionable_excluded)
                        else '有内容未携带，请核对排除清单并从原位置补齐；有来源的技能可重新安装。')
                record['reinstall']={'method':'source' if origin['source']['url'] else 'manual','hint':hint}
                for entry in writer.entries:
                    if entry.get('provenance_id')==record['id']:
                        entry['flags'].append(f"artifacts_excluded:{len(actionable_excluded)}")
            if origin['origin']=='unknown':
                result.warnings.append({'code':'E7505','message':'一个技能的来源不明，已保存可携带内容；请核对技能来源报告。'})
    return result


def _record(name: str, holder: str, via: str, origin: dict) -> dict:
    return {'name':safe_name(name),'holder':holder,'via':via,**origin,'files':0,'bytes':0,'content_sha256':None,
            'skill_md_sha256':None,'excluded':[],'carried':'record_only','reinstall':None}


def skills_report(records: list[dict]) -> dict:
    # Assign IDs to record-only/account records without disturbing payload references.
    used={r['id'] for r in records if 'id' in r}
    for record in records:
        if 'id' not in record:
            number=1
            while f's{number:04d}' in used:number+=1
            record['id']=f's{number:04d}';used.add(record['id'])
    names={r['name'] for r in records};copies=[]
    for name in sorted(names):
        members=[r for r in records if r['name']==name]
        if len(members)>1:
            hashes=[r['skill_md_sha256'] for r in members]
            relation=('identical' if len(set(hashes))==1 else 'diverged') if all(hashes) else 'unverified'
            copies.append({'name':name,'members':[r['id'] for r in members],'relation':relation,'skill_md_sha256':hashes})
    summary={'total':len(records),'own':sum(r['origin']=='user' for r in records),'third_party':sum(r['origin']=='third_party' for r in records),
             'vendor_builtin':sum(r['origin']=='vendor_builtin' for r in records),'unknown_source':sum(r['origin']=='unknown' for r in records),
             'diverged_copies':sum(c['relation']=='diverged' for c in copies),
             'unverified_copies':sum(c['relation']=='unverified' for c in copies)}
    return {'schema':1,'skills':records,'copies':copies,'summary':summary}


def skills_markdown(report: dict) -> str:
    lines=['# 技能来源与副本','']
    labels={'user':'自己创建','third_party':'第三方来源','vendor_builtin':'应用内置（仅记录）','unknown':'来源不明'}
    for record in report['skills']:
        lines.append(f"- {record['name']}：{labels[record['origin']]}；已保存 {record['files']} 个文件。")
        if record['source']['url']:lines.append('  来源：'+record['source']['url'])
        if any(e['reason'] != 'git_metadata_excluded' for e in record.get('excluded', [])):
            lines.append('  有可重新生成或超出上限的文件未携带，请按来源说明重装或构建。')
        elif record.get('excluded'):
            lines.append('  Git 信息已按要求排除，无需补齐。')
    for copies in report['copies']:
        relation={'identical':'内容相同','diverged':'内容不同','unverified':'缺少可比较的正文摘要，尚未核对'}[copies['relation']]
        lines.append(f"- 同名技能 {copies['name']}：{relation}，可携带的各份分别保留。")
    return '\n'.join(lines)+'\n'

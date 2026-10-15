"""Account skills are carried for export, never restored into an application cache."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Mapping

from .bundle import BundleError, BundleWriter, _member_name
from .collect_classified import read_source
from .collect_tier1 import CollectionResult
from .config import MachineConfig, excluded_path
from .coverage import no_links, safe_name
from .catalog import classify
from .source_roots import desktop_root


@dataclass
class DesktopSkillsResult(CollectionResult):
    skills: list[dict] = field(default_factory=list)


def manifest_skills(raw: dict) -> dict[str, str]:
    """Supported keyed/list skill manifests; unknown creator types are never inferred."""
    entries = raw.get('skills', {})
    values = entries.items() if isinstance(entries, dict) else (
        ((entry.get('name'), entry) for entry in entries if isinstance(entry, dict)) if isinstance(entries, list) else ())
    result = {}
    for name, entry in values:
        if not isinstance(name, str) or '/' in name or '\\' in name or not isinstance(entry, dict):
            continue
        try:
            _member_name('skills/' + name + '/SKILL.md')
        except BundleError:
            continue
        creator = entry.get('creatorType')
        if creator in {'user', 'anthropic'}:
            result[name] = creator
    return result


def collect_desktop_skills(writer: BundleWriter, *, home: Path, config: MachineConfig,
                           environ: Mapping[str,str], agents: frozenset[str], os_name: str) -> DesktopSkillsResult:
    result = DesktopSkillsResult()
    if 'claude' not in agents:
        return result
    desktop = desktop_root(home, environ)
    if desktop is None:
        return result
    root = desktop/'local-agent-mode-sessions/skills-plugin'
    def allowed(path: Path) -> bool:
        return no_links(path) and not excluded_path(path,config=config,home=home,os_name=os_name,boundary=desktop)
    def failure(logical: str, reason: str) -> None:
        result.exclusions.append({'logical_path':logical,'reason':reason})
        result.coverage_issues.setdefault('claude_desktop',set()).add(reason)
        result.warnings.append({'code':'E7101','message':'一个账号技能来源无法读取，已跳过，请核对排除清单。'})
    def directory(path: Path, logical: str) -> bool:
        if not allowed(path):
            return False
        try:
            return stat.S_ISDIR(path.stat().st_mode)
        except FileNotFoundError:
            return False
        except OSError:
            failure(logical,'metadata_unreadable')
            return False
    def children(path: Path, logical: str) -> list[Path]:
        try:
            return sorted(path.iterdir())
        except OSError:
            failure(logical,'enumeration_failed')
            return []
    if not directory(root,'claude:desktop/accounts'):
        return result
    accounts = []
    for account_number, account in enumerate(children(root,'claude:desktop/accounts'),1):
        account_logical = f'claude:desktop/account-directory-{account_number:04d}'
        if not directory(account,account_logical):
            continue
        for organization_number, organization in enumerate(children(account,account_logical),1):
            logical = f'{account_logical}/organization-{organization_number:04d}'
            if not directory(organization,logical):
                continue
            try:
                if stat.S_ISREG((organization/'manifest.json').stat().st_mode):
                    accounts.append(organization)
            except FileNotFoundError:
                continue
            except OSError:
                failure(logical+'/manifest.json','metadata_unreadable')
    for number, folder in enumerate(accounts, 1):
        alias = f'a{number:04d}'
        manifest = read_source(folder/'manifest.json',desktop,result)
        if manifest is None:
            failure(f'claude:desktop/{alias}/manifest.json','unreadable')
            continue
        try:
            raw = json.loads(manifest) if manifest is not None else {}
            if not isinstance(raw, dict):
                raise ValueError()
            declared = manifest_skills(raw)
        except (ValueError, UnicodeError):
            result.warnings.append({'code':'E7102','message':'一个账号技能清单无法解析，已跳过该账号。'})
            continue
        for name, creator in sorted(declared.items()):
            skill = folder/'skills'/name
            result.coverage_origins[skill] = 'user' if creator == 'user' else 'vendor_builtin'
            record = {'account':alias,'name':safe_name(name),'holder':'claude-desktop-account',
                      'origin':'user' if creator == 'user' else 'vendor_builtin',
                      'source':{'kind':'account','url':None,'ref':None,'evidence':'manifest.creatorType','confidence':'exact'},
                      'carried':'partial' if creator == 'user' else 'record_only', 'files':0,'bytes':0,
                      'content_sha256':None,'skill_md_sha256':None,'excluded':[]}
            result.skills.append(record)
            # Vendor content is recorded by manifest alone, with zero body reads.
            logical_skill = f'claude:desktop/{alias}/skills/{name}'
            if creator != 'user' or not writer.wants('skills','skills_own') or not allowed(skill):
                record['carried']='record_only'
                continue
            exclusion_count = len(result.exclusions)
            if not directory(skill,logical_skill):
                reason = 'metadata_unreadable' if len(result.exclusions) > exclusion_count else 'unreadable'
                if len(result.exclusions) == exclusion_count:
                    failure(logical_skill,reason)
                record['excluded'].append({'path':'<技能目录>','size':None,'reason':reason})
                continue
            hashes = []; partial = False
            def eligible(path: Path) -> bool:
                return allowed(path) and classify('claude_desktop', path.relative_to(desktop).as_posix(), origin='user').action != 'never'
            def enumeration_failed(error: OSError) -> None:
                nonlocal partial
                partial = True
                path = Path(error.filename) if error.filename else skill
                relative = path.relative_to(skill).as_posix() if path.is_relative_to(skill) and path != skill else '<技能目录>'
                record['excluded'].append({'path':safe_name(relative),'size':None,'reason':'enumeration_failed'})
                failure(logical_skill+'/'+relative,'enumeration_failed')
            def files():
                for parent, directories, names in os.walk(skill,followlinks=False,onerror=enumeration_failed):
                    base = Path(parent)
                    directories[:] = [name for name in directories if eligible(base/name)]
                    for name in sorted(names):
                        source = base/name
                        if eligible(source):
                            yield source
            for source in files():
                relative = source.relative_to(skill).as_posix()
                logical = f'claude:desktop/{alias}/skills/{name}/{relative}'
                result.coverage_logical[source] = logical
                archive = f'files/claude/desktop/accounts/{alias}/skills/{name}/{relative}'
                try:
                    metadata = source.stat()
                except OSError:
                    partial = True
                    failure(logical,'metadata_unreadable')
                    record['excluded'].append({'path':safe_name(relative),'size':None,'reason':'metadata_unreadable'})
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    continue
                if len(archive) > 240:
                    partial = True
                    size = metadata.st_size
                    writer.oversize.append({'logical_path':logical,'size':size,'reason':'path_too_long'})
                    record['excluded'].append({'path':safe_name(relative),'size':size,'reason':'path_too_long'})
                    continue
                data = read_source(source,desktop,result)
                if data is None:
                    partial = True
                    result.exclusions.append({'logical_path':logical,'reason':'unreadable'})
                    record['excluded'].append({'path':safe_name(relative),'size':None,'reason':'unreadable'})
                    continue
                data, flags = writer.prepare_content(data,logical_path=logical,rule_id='CD-01',origin='user',confidence='exact',format_hint=source.suffix)
                if data is None:
                    partial = True
                    result.exclusions.append({'logical_path':logical,'reason':'secret_hit' if writer.flagged_policy=='skip' else 'skipped_by_policy'})
                    continue
                added = writer.add_file(archive,data,
                                       agent='claude',instance='desktop',kind='skills',logical_path=logical,restore='export',
                                       flags=flags,rule_id='CD-01',nature='A',group='skills_own',holder='claude-desktop-account',
                                       conflict_group=f'skill:{alias}:{name}',
                                       redactions=sum(int(f.split(':')[1]) for f in flags if f.startswith('redacted:')))
                if added:
                    partial = partial or any(f.startswith('redacted:') for f in flags)
                    digest = hashlib.sha256(data).hexdigest()
                    hashes.append((relative,digest));record['files']+=1;record['bytes']+=len(data)
                    if relative == 'SKILL.md':
                        record['skill_md_sha256'] = digest
                else:
                    partial = True
            record['content_sha256'] = hashlib.sha256(json.dumps(sorted(hashes),ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
            if record['files']:
                record['carried'] = 'partial' if partial else 'verbatim'
    return result

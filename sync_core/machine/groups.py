"""Stable content groups, including legacy bundle inference."""
from __future__ import annotations

GROUP_LABELS = {'rules':'规则','memory':'记忆与笔记','skills_own':'我写的技能与脚本',
                'skills_third':'第三方技能（含来源）','approvals':'已批准的操作','settings':'设置与信任',
                'history':'历史记录（体积较大）'}
DEFAULT_GROUPS = frozenset(GROUP_LABELS)-{'history'}
_KINDS = {'rules':'rules','memory':'memory','persona':'memory','plans':'memory','skills':'skills_own',
          'skills_text':'skills_own','customizations':'skills_own','scripts':'skills_own',
          'approvals':'approvals','permissions_local':'approvals','settings_fields':'settings',
          'trust_fields':'settings','env_fields':'settings','history_files':'history'}


def entry_group(entry: dict) -> str | None:
    return entry.get('group') or _KINDS.get(entry.get('kind'))


def selected_groups(groups: frozenset[str] | None) -> frozenset[str]:
    if groups is None:return DEFAULT_GROUPS
    if not isinstance(groups,frozenset) or any(not isinstance(g,str) or g not in GROUP_LABELS for g in groups):
        raise ValueError('invalid content groups')
    return groups


def group_counts(entries) -> dict:
    counts={}
    for entry in entries:
        group=entry_group(entry)
        if group:
            count=counts.setdefault(group,{'files':0,'bytes':0})
            count['files']+=1;count['bytes']+=entry['size']
    return counts

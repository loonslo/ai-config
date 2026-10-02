import tomllib

import pytest

from test_machine_preflight import fixture_bundle
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore,apply_restore


def test_confirmed_trust_preserves_comments_unknown_fields_and_is_idempotent(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    target=home/'.codex/config.toml'
    target.write_text('# keep this comment\nmodel_reasoning_effort = "high"\n[unknown]\nx = 42\n',encoding='utf-8')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    with pytest.raises(ValueError,match='confirmation'):
        plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,
                     codex_trust=True,confirm_trust='bad')
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,
                      codex_trust=True,confirm_trust=check.trust_list_hash)
    apply_restore(plan,processes=[])
    text=target.read_text(encoding='utf-8')
    assert text.startswith('# keep this comment\n')
    raw=tomllib.loads(text)
    assert raw['unknown']['x']==42
    path=check.trust_list[0]['path']
    assert set(raw['projects'])=={path}
    assert raw['projects'][path]['trust_level']=='trusted'
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,
                      codex_trust=True,confirm_trust=check.trust_list_hash)
    assert not plan.changes


def test_trust_conflict_preserved_and_displayed_list_mutation_rejected(tmp_path):
    bundle,home,project,config,mapper=fixture_bundle(tmp_path)
    path=str(project).replace('\\','/').lower()
    target=home/'.codex/config.toml'
    original=f"[projects.'{path}']\ntrust_level = 'untrusted'\n"
    target.write_text(original,encoding='utf-8')
    check=preflight(bundle,home=home,config=config,root_map=mapper,environ={},processes=[])
    shown=check.trust_list_hash
    plan=plan_restore(check,state=home/'.ai-sync/state',process_names=config.running_process_names,
                      codex_trust=True,confirm_trust=shown)
    assert any(item['reason']=='trust_differs' for item in plan.conflicts)
    apply_restore(plan,processes=[])
    assert tomllib.loads(target.read_text())['projects'][path]['trust_level']=='untrusted'
    check.trust_list[0]['path'] += '-changed'
    with pytest.raises(ValueError,match='changed'):
        apply_restore(plan,processes=[])

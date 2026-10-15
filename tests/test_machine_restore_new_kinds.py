import io
import json
import zipfile

import pytest

from sync_core.machine.bundle import BundleError, BundleWriter
from sync_core.machine.config import load_config
from sync_core.machine.preflight import preflight
from sync_core.machine.apply import plan_restore, apply_restore
from sync_core.machine.verify import verify


def test_export_only_writes_report_directory_and_skill_zip_top_level(tmp_path):
    home = tmp_path / 'home'
    home.mkdir()
    writer = BundleWriter(tmp_path / 'source.zip', source={'os':'windows'})
    for name, data in [('SKILL.md', b'account skill'), ('data.bin', b'\x00\xff')]:
        writer.add_file('files/claude/desktop/skills/diary/' + name, data, agent='claude', instance='desktop', kind='skills',
                        logical_path='claude:desktop/skills/diary/' + name, restore='export', conflict_group='skill:diary')
    env = {'fields': {'AI_BASE_URL': "https://example.org/a'b"}}
    writer.add_file('files/system/main/env.fields.json', json.dumps(env).encode(), agent='system', instance='main', kind='env_fields',
                    logical_path='system:main/user-env', restore='export')
    writer.finalize()
    report = tmp_path / 'reports'
    check = preflight(writer.destination, home=home, config=load_config(tmp_path/'missing.json', home=home), environ={}, processes=[], report_dir=report)
    plan = plan_restore(check, state=tmp_path/'state', process_names=())
    assert not report.exists() and not plan.changes
    first = dict(plan.export_changes)
    second = plan_restore(check, state=tmp_path/'state', process_names=()).export_changes
    assert first == second
    apply_restore(plan, processes=[])
    assert not (home/'.claude').exists() and not (home/'.codex').exists()
    with zipfile.ZipFile(report/'account-skills/diary.zip') as archive:
        assert set(archive.namelist()) == {'diary/SKILL.md','diary/data.bin'}
        assert archive.read('diary/data.bin') == b'\x00\xff'
    assert "a''b" in (report/'restore-env.ps1').read_text(encoding='utf-8-sig')
    assert not (tmp_path/'state/backups').exists()
    checks = verify(check, restored=plan.restored, skipped=plan.skipped).checks
    assert all(c['status']=='MANUAL' and c['reason']=='exported' for c in checks if c.get('entry_id'))


def test_exports_cannot_write_inside_agent_root_or_overwrite_after_preview(tmp_path):
    home = tmp_path/'home'
    (home/'.codex').mkdir(parents=True)
    writer = BundleWriter(tmp_path/'source.zip', source={'os':'windows'})
    writer.add_file('files/system/main/env.fields.json', b'{"fields":{"AI_TEST":"example"}}', agent='system', instance='main', kind='env_fields', logical_path='system:main/user-env', restore='export')
    writer.finalize()
    config = load_config(tmp_path/'missing.json', home=home)
    with pytest.raises(BundleError, match='inside'):
        preflight(writer.destination, home=home, config=config, environ={}, processes=[], report_dir=home/'.codex/reports')
    reports = tmp_path/'reports'
    check = preflight(writer.destination, home=home, config=config, environ={}, processes=[], report_dir=reports)
    plan = plan_restore(check, state=tmp_path/'state', process_names=())
    reports.mkdir()
    (reports/'restore-env.ps1').write_bytes(b'local')
    with pytest.raises(BundleError, match='changed'):
        apply_restore(plan, processes=[])
    assert (reports/'restore-env.ps1').read_bytes() == b'local'

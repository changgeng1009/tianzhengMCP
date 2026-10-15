"""Distribution fixtures must never masquerade as vendor commands or live evidence."""
import json
from pathlib import Path

PACK = Path('tianzheng_command_registry_pack/tianzheng_command_registry_pack')

def test_copies_consistent_and_original():
    paths = [Path('tianzheng_commands.seed.json'), Path('command_registry/tianzheng_commands.seed.json'), PACK / 'registries/tianzheng_commands.seed.json']
    data = [json.loads(p.read_text(encoding='utf-8')) for p in paths]
    assert data[0] == data[1] == data[2]
    for registry in data:
        assert registry['synthetic'] is True
        assert registry['execution_allowed'] is False
        assert set(registry['source_catalog']) == {'original_synthetic_fixture'}
        assert len(registry['commands']) == 6
        for command in registry['commands']:
            assert command['synthetic'] is True
            assert command['execution_allowed'] is False
            assert command['primary_command'].startswith('SYNTHETIC_FIXTURE_')
            assert command['source_ids'] == ['original_synthetic_fixture']
            assert command['source_status'] == 'synthetic'
            assert command['validation_status']['source_status'] == 'synthetic'
            assert command['validation_status']['sandbox'] == 'not_started'
            assert command['validation_status']['production'] == 'forbidden'
            assert command['local_discovery_evidence'] == []
            assert command['confirmed'] is False
            assert command['confirmed_for_sandbox'] is False
            assert command['safety']['allow_sandbox'] is False
            assert command['safety']['allow_production'] is False

def test_synthetic_cannot_be_promoted():
    data = json.loads(Path('command_registry/source_status_model.json').read_text(encoding='utf-8'))
    status = data['source_statuses']['synthetic']
    assert status['can_be_confirmed'] is False
    assert status['can_be_used_for_production'] is False
    assert status['next_status'] is None

def test_domain_copies_match():
    full = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
    for domain, folder, filename in [('plumbing', 'water', 'plumbing_commands.seed.json'), ('hvac', 'hvac', 'hvac_commands.seed.json')]:
        expected = [c for c in full['commands'] if c['domain'] == domain]
        for path in [Path('command_registry') / folder / filename, PACK / 'registries' / filename]:
            assert json.loads(path.read_text(encoding='utf-8'))['commands'] == expected

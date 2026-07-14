import json, pytest
from pathlib import Path

class TestSourceProtection:
    def test_r6_no_source_save(self):
        r = json.loads(Path('artifacts/t30_r6_persistence.json').read_text(encoding='utf-8'))
        assert r['save_called_on_source'] is False
        assert r['source_dwg_opened'] is False
        assert r['d1_allowed'] is False

    def test_r5_1_no_source(self):
        r = json.loads(Path('artifacts/t30_r5_1_diff_result.json').read_text(encoding='utf-8'))
        assert r.get('d1_allowed', False) is False
        assert r.get('script_sendcommand_used', False) is False

    def test_dangerous_from_seed(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        dangerous = [c for c in seed['commands'] if c['safety']['danger_level'] == 'dangerous']
        assert len(dangerous) == 3
        for command in dangerous:
            assert command['synthetic'] is True
            assert command['execution_allowed'] is False
            assert command['safety']['allow_sandbox'] is False
            assert command['safety']['allow_production'] is False

    @pytest.mark.parametrize('name', ['TSaveAs', 'dcsz', 'tgbatplots'])
    def test_vendor_dangerous_names_still_rejected_when_misclassified(self, name):
        from command_registry.tools.validate_registry import validate_registry
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        fixture = seed['commands'][0]
        fixture['primary_command'] = name
        fixture['safety']['danger_level'] = 'low'
        assert validate_registry([fixture])['errors']

    def test_all_fixture_commands_production_forbidden(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        assert seed['commands']
        for command in seed['commands']:
            assert command['validation_status']['production'] == 'forbidden'
            assert command['safety']['allow_production'] is False

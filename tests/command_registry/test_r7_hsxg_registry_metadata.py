import json, pytest
from pathlib import Path

class TestHSXGMetadata:
    def test_synthetic_review_in_registry(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        hsxg = [c for c in seed['commands'] if c.get('primary_command') == 'SYNTHETIC_FIXTURE_02']
        assert len(hsxg) >= 1

    def test_synthetic_review_production_forbidden(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        for c in seed['commands']:
            if c.get('primary_command') == 'SYNTHETIC_FIXTURE_02':
                assert c['validation_status']['production'] == 'forbidden'
                assert c['safety']['allow_production'] is False

    def test_all_allow_production_false(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        for c in seed['commands']:
            assert c['safety']['allow_production'] is False

    def test_dangerous_commands_unchanged(self):
        seed = json.loads(Path('command_registry/tianzheng_commands.seed.json').read_text(encoding='utf-8'))
        dangerous = [c for c in seed['commands'] if c['safety']['danger_level'] == 'dangerous']
        assert len(dangerous) == 3

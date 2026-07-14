import json, pytest
from pathlib import Path

class TestD71RealTasks:
    def test_task_count(self):
        r = json.loads(Path('reports/phase_d7_1_redraw_task_plan.json').read_text(encoding='utf-8'))
        assert r['task_count'] > 0

    def test_add_tasks(self):
        r = json.loads(Path('reports/phase_d7_1_redraw_task_plan.json').read_text(encoding='utf-8'))
        assert r['add_task_count'] >= 0

    def test_executable_present(self):
        r = json.loads(Path('reports/phase_d7_1_redraw_task_plan.json').read_text(encoding='utf-8'))
        assert 'executable_task_count' in r

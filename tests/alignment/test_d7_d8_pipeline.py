from mcp.redraw_planner.task_planner import plan_redraw_tasks
from mcp.execution_strategy.execution_engine import plan_execution

class TestD7D8Pipeline:
    def test_plan_empty(self):
        r = plan_redraw_tasks({'diff': {}})
        assert r['total_tasks'] == 0

    def test_plan_add(self):
        r = plan_redraw_tasks({'diff': {'TDbPipe': {'reference': 0, 'target': 5, 'delta': 5, 'action': 'add'}}})
        assert r['total_tasks'] == 1
        assert r['total_additions'] == 1

    def test_plan_remove(self):
        r = plan_redraw_tasks({'diff': {'TDbPipe': {'reference': 5, 'target': 0, 'delta': -5, 'action': 'remove'}}})
        assert r['total_removals'] == 1

    def test_execution_blocked(self):
        plan = plan_redraw_tasks({'diff': {'TDbPipe': {'reference': 0, 'target': 5, 'delta': 5, 'action': 'add'}}})
        exec_plan = plan_execution(plan)
        assert exec_plan['production_blocked'] is True
        assert exec_plan['d1_allowed'] is False

    def test_source_never_opened(self):
        plan = plan_redraw_tasks({'diff': {}})
        assert plan['source_dwg_opened'] is False
        assert plan['d1_allowed'] is False

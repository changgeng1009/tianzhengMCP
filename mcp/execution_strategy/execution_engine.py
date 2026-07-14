import json, datetime

def plan_execution(task_plan):
    stages = []
    for task in task_plan.get('diff_based_tasks', []):
        stage = {
            'object_type': task['object_type'],
            'action': task['action'],
            'count': task['count'],
            'sandbox_allowed': task['action'] == 'add',
            'requires_approval': task['requires_visual_confirm'],
            'production_forbidden': True,
            'd1_blocked': True
        }
        stages.append(stage)
    return {
        'phase': 'D8',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'execution_stages': stages,
        'total_stages': len(stages),
        'sandbox_ready_stages': sum(1 for s in stages if s['sandbox_allowed']),
        'production_blocked': True,
        'd1_allowed': False, 'source_dwg_opened': False
    }

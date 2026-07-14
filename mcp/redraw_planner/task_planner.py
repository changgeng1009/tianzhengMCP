import json, datetime

def plan_redraw_tasks(diff_report):
    tasks = []
    diff = diff_report.get('diff', {})
    for obj_type, info in sorted(diff.items()):
        delta = info['delta']
        if delta > 0:
            action = 'add'
            count = delta
        elif delta < 0:
            action = 'remove'
            count = -delta
        else:
            continue
        tasks.append({
            'object_type': obj_type,
            'action': action,
            'count': abs(count),
            'strategy': 'sandbox_dry_run' if action != 'remove' else 'review_only',
            'requires_visual_confirm': action in ('add', 'remove')
        })
    return {
        'phase': 'D7',
        'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'diff_based_tasks': tasks,
        'total_tasks': len(tasks),
        'total_additions': sum(1 for t in tasks if t['action'] == 'add'),
        'total_removals': sum(1 for t in tasks if t['action'] == 'remove'),
        'source_dwg_opened': False, 'd1_allowed': False
    }

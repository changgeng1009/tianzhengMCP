import json, datetime

def validate_redraw(before_scan, after_scan, diff_report):
    checks = []
    if after_scan.get('total_entities', 0) >= before_scan.get('total_entities', 0):
        checks.append({'check':'entity_count','passed':True,'detail':'After >= Before'})
    else:
        checks.append({'check':'entity_count','passed':False})
    passed = all(c['passed'] for c in checks)
    return {
        'phase':'D10',
        'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'qa_passed':passed,
        'checks':checks,
        'source_dwg_opened':False,'d1_allowed':False
    }

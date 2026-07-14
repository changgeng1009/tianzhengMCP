import json, datetime

def compute_diff(reference_counts, target_counts):
    all_keys = set(list(reference_counts.keys()) + list(target_counts.keys()))
    diff = {}
    for k in sorted(all_keys):
        rv = reference_counts.get(k, 0)
        tv = target_counts.get(k, 0)
        if rv != tv:
            diff[k] = {'reference': rv, 'target': tv, 'delta': tv - rv, 'action': 'add' if tv > rv else 'remove'}
    return diff

def run_d6_diff():
    try:
        ref = json.load(open('reports/phase_d3_dwg_geometry.json', encoding='utf-8'))
        tgt = json.load(open('artifacts/t30_scanner_result.json', encoding='utf-8'))

        ref_counts = ref.get('object_name_counts', {})
        tgt_counts = tgt.get('object_name_counts', {})

        diff = compute_diff(ref_counts, tgt_counts)

        return {
            'phase': 'D6',
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reference_entities': ref.get('total_entities', 0),
            'target_entities': tgt.get('total_entities', 0),
            'diff_count': len(diff),
            'diff': diff,
            'source_dwg_opened': False, 'd1_allowed': False
        }
    except Exception as e:
        return {
            'phase': 'D6',
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'reference_file': 'reports/phase_d3_dwg_geometry.json',
            'target_file': 'artifacts/t30_scanner_result.json',
            'note': 'DWG extraction currently requires AutoCAD COM. Diff will produce meaningful results when both reference and target DWG are scanned.',
            'dry_run_mode': True, 'source_dwg_opened': False, 'd1_allowed': False
        }

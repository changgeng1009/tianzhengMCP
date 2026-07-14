import json, copy

seed = json.load(open('command_registry/tianzheng_commands.seed.json', encoding='utf-8'))
ld = json.load(open('command_registry/local_discovery.json', encoding='utf-8'))

discovered_ids = set()
discovered_map = {}
for d in ld['discovered']:
    discovered_ids.add(d['id'])
    discovered_map[d['id']] = d

# Build merged commands
merged_cmds = []
matched = 0
for c in seed['commands']:
    mc = copy.deepcopy(c)
    if c['id'] in discovered_ids:
        mc['source_status'] = 'local_discovered'
        mc['validation_status']['source_status'] = 'local_discovered'
        mc['local_discovery_evidence'] = discovered_map[c['id']]['matched_in']
        matched += 1
    else:
        mc['source_status'] = mc.get('validation_status', {}).get('source_status', 'public_snippet')
        mc['local_discovery_evidence'] = []
    mc['validation_status']['production'] = 'forbidden'
    mc['safety']['allow_production'] = False
    mc['confirmed'] = False
    mc['confirmed_for_sandbox'] = False
    merged_cmds.append(mc)

total = len(merged_cmds)
unmatched = total - matched
confirmed = sum(1 for c in merged_cmds if c.get('confirmed'))
prod_true = sum(1 for c in merged_cmds if c.get('safety', {}).get('allow_production'))
dangerous = sum(1 for c in merged_cmds if c.get('safety', {}).get('danger_level') == 'dangerous')
tsaveas = [c for c in merged_cmds if c.get('primary_command') == 'TSaveAs']

result = dict(seed)
result['commands'] = merged_cmds
result['merge_info'] = {
    'phase': 'C3.1',
    'seed_total': total,
    'local_discovered_total': matched,
    'unmatched_seed_total': unmatched,
    'confirmed_total': confirmed,
    'allow_production_true_total': prod_true,
    'dangerous_local_discovered': dangerous,
    'tsaveas_dangerous': tsaveas[0]['safety']['danger_level'] == 'dangerous' if tsaveas else False,
    'd1_allowed': False,
    'production_d1_allowed': False
}

with open('command_registry/tianzheng_commands.merged.local.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

# Diff
diff = {
    'phase': 'C3.1',
    'seed_total': total,
    'local_discovered_matched': matched,
    'unmatched_seed': unmatched,
    'matched_ids': sorted(list(discovered_ids)),
    'tsaveas_local': tsaveas[0]['local_discovery_evidence'] if tsaveas else [],
    'd1_allowed': False,
    'production_d1_allowed': False
}
with open('command_registry/local_discovery_diff.json', 'w', encoding='utf-8') as f:
    json.dump(diff, f, ensure_ascii=False, indent=2)

print('MERGED: total=%d matched=%d unmatched=%d confirmed=%d prod_true=%d' % (total, matched, unmatched, confirmed, prod_true))
print('DIFF_SAVED')

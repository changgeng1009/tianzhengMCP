import json, os
from collections import Counter

data = json.load(open('tianzheng_commands.seed.json', encoding='utf-8'))
os.makedirs('command_registry/water', exist_ok=True)
os.makedirs('command_registry/hvac', exist_ok=True)
os.makedirs('command_registry/tools', exist_ok=True)
os.makedirs('tests/command_registry', exist_ok=True)

# Split
plumbing = [c for c in data['commands'] if c['domain'] == 'plumbing']
hvac = [c for c in data['commands'] if c['domain'] == 'hvac']

json.dump(data, open('command_registry/tianzheng_commands.seed.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
pl = dict(data); pl['commands'] = plumbing; pl['domains'] = {k:v for k,v in data['domains'].items() if k=='plumbing'}
json.dump(pl, open('command_registry/water/plumbing_commands.seed.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
hv = dict(data); hv['commands'] = hvac; hv['domains'] = {k:v for k,v in data['domains'].items() if k=='hvac'}
json.dump(hv, open('command_registry/hvac/hvac_commands.seed.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)

# Validate
ids = [c['id'] for c in data['commands']]
dangerous = [c for c in data['commands'] if c['safety']['danger_level'] == 'dangerous']
review = [c for c in data['commands'] if c['safety']['danger_level'] == 'review']
sandbox_safe = [c for c in data['commands'] if c['safety']['danger_level'] == 'sandbox_safe']
prod_true = [c for c in data['commands'] if c['safety'].get('allow_production') == True]
missing = [c['id'] for c in data['commands'] if not c.get('id') or not c.get('domain') or not c.get('primary_command')]
has_source = sum(1 for c in data['commands'] if c.get('source_ids'))
cats = Counter(c.get('category','?') for c in data['commands'])

print('TOTAL:', len(data['commands']))
print('PLUMBING:', len(plumbing))
print('HVAC:', len(hvac))
print('DANGEROUS:', len(dangerous))
print('REVIEW:', len(review))
print('SANDBOX_SAFE:', len(sandbox_safe))
print('PROD_TRUE:', len(prod_true))
print('MISSING_FIELDS:', len(missing))
print('HAS_SOURCE:', has_source)
print('CATEGORIES:', dict(cats))
if dangerous: print('DANGEROUS_CMDS:', [c['primary_command'] for c in dangerous])

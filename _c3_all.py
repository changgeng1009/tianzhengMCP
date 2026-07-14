import json, re, os

def parse_tmn(path):
    cmds = set()
    with open(path, encoding='utf-8', errors='ignore') as f:
        text = f.read()
    for m in re.finditer(r'(?<![a-zA-Z])([A-Z][A-Za-z_0-9]{2,30})', text):
        cmd = m.group(1)
        if re.match(r'^[A-Z]', cmd) and not cmd.startswith(('AND','THE','END','FOR','NOT')):
            cmds.add(cmd)
    return cmds

def deep_tmn(path):
    cmds = set()
    with open(path, encoding='utf-8', errors='ignore') as f:
        text = f.read()
    for m in re.finditer(r'\b(T88_\w+|TSaveAs|TSetMenu\s+[^)]+\)|T96_\w+|TCH_\w+)\b', text):
        cmds.add(m.group(1))
    return cmds

BASE_P = r'D:\Tangent\TwtT30V1'
BASE_H = r'C:\Tangent\THvacT30V1'

pt = set(); ht = set(); ptd = set(); htd = set()
for s in ['sys','sys19x64','sys20x64','sys21x64','sys22x64','sys23x64','sys24x64','sys25x64']:
    for t in ['TCH.TMN','OUT.TMN']:
        p = os.path.join(BASE_P,s,t)
        if os.path.exists(p): pt |= parse_tmn(p); ptd |= deep_tmn(p)
    for t in ['TCH.TMN']:
        p = os.path.join(BASE_H,s,t)
        if os.path.exists(p): ht |= parse_tmn(p); htd |= deep_tmn(p)

# Seed
seed = json.load(open('command_registry/tianzheng_commands.seed.json', encoding='utf-8'))

discovered = {}
for c in seed['commands']:
    d = c['domain']
    primary = (c.get('primary_command','') or '').strip()
    tmn_set = pt if d == 'plumbing' else ht
    tmn_deep = ptd if d == 'plumbing' else htd
    matched = []
    # Broad
    if primary and primary in tmn_set: matched.append('tmn')
    # Deep
    if primary and primary in tmn_deep: matched.append('tmn_deep')
    # Partial
    if not matched:
        for pat in [primary]:
            if not pat: continue
            for tm in tmn_deep:
                if pat.lower() in tm.lower() or tm.lower() in pat.lower():
                    matched.append('tmn_partial')
                    break
    if matched:
        discovered[c['id']] = {'id':c['id'],'domain':d,'primary_command':primary,'matched_in':matched}

disc = list(discovered.values())
dc = sum(1 for d in disc if d['domain']=='plumbing')
dh = sum(1 for d in disc if d['domain']=='hvac')
print(f'DISCOVERED: {len(disc)} (P:{dc} H:{dh})')
for d in disc:
    print(f'  [{d["domain"]}] {d["id"]}: {d["primary_command"]} <- {d["matched_in"]}')

with open('command_registry/local_discovery.json','w',encoding='utf-8') as f:
    json.dump({'phase':'C3','local_installation_scanned':True,'plumbing_path':BASE_P,'hvac_path':BASE_H,
        'tmn_plumbing':len(pt),'tmn_hvac':len(ht),'tmn_deep_plumbing':len(ptd),'tmn_deep_hvac':len(htd),
        'total_discovered':len(disc),'by_domain':{'plumbing':dc,'hvac':dh},'discovered':disc,
        'd1_allowed':False,'production_d1_allowed':False,'autocad_connected':False,'dwg_opened':False},
        f,ensure_ascii=False,indent=2)
print(f'SAVED: {len(disc)} discoveries')

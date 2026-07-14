import json, re, os

def parse_pgp(path):
    aliases = {}
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith(';') and '=' in line:
                parts = line.split(',')
                kv = parts[0].strip()
                if '=' in kv:
                    k, v = kv.split('=', 1)
                    k, v = k.strip().upper(), v.strip()
                    if k and v and len(k) <= 10:
                        aliases[k] = v
    return aliases

def parse_tmn(path):
    cmds = set()
    with open(path, encoding='utf-8', errors='ignore') as f:
        text = f.read()
    for m in re.finditer(r'(?<![a-zA-Z])([A-Z][A-Za-z_0-9]{2,30})', text):
        cmd = m.group(1)
        if re.match(r'^[A-Z]', cmd) and not cmd.startswith(('AND','THE','END','FOR','NOT')):
            cmds.add(cmd)
    return cmds

BASE_P = r'D:\Tangent\TwtT30V1'
BASE_H = r'C:\Tangent\THvacT30V1'

# PGP
pa = parse_pgp(os.path.join(BASE_P, 'sys', 'acad.pgp'))
ha = parse_pgp(os.path.join(BASE_H, 'sys', 'acad.pgp'))

# TMN
pt = set(); ht = set()
for s in ['sys','sys19x64','sys20x64','sys21x64','sys22x64','sys23x64','sys24x64','sys25x64']:
    for t in ['TCH.TMN','OUT.TMN']:
        p = os.path.join(BASE_P,s,t)
        if os.path.exists(p): pt |= parse_tmn(p)
    p = os.path.join(BASE_H,s,'TCH.TMN')
    if os.path.exists(p): ht |= parse_tmn(p)

# Seed
seed = json.load(open('command_registry/tianzheng_commands.seed.json', encoding='utf-8'))

discovered = []
for c in seed['commands']:
    d = c['domain']
    primary = (c.get('primary_command','') or '').upper()
    aliases_list = [a.upper() for a in c.get('aliases',[])]
    pgp_src = pa if d == 'plumbing' else ha
    tmn_set = pt if d == 'plumbing' else ht
    matched = []
    if primary and primary in pgp_src: matched.append('pgp_primary')
    for a in aliases_list:
        if a in pgp_src: matched.append(f'pgp_alias:{a}')
    if primary and primary in tmn_set: matched.append('tmn')
    if matched:
        discovered.append({'id':c['id'],'domain':d,'primary_command':primary,'matched_in':matched})

dc = sum(1 for d in discovered if d['domain']=='plumbing')
dh = sum(1 for d in discovered if d['domain']=='hvac')
print(f'DISCOVERED:{len(discovered)} P:{dc} H:{dh}')
print(f'PGP_P:{len(pa)} PGP_H:{len(ha)} TMN_P:{len(pt)} TMN_H:{len(ht)}')
for d in discovered[:8]: print(f'  {d["id"]} <- {d["matched_in"]}')

with open('command_registry/local_discovery.json','w',encoding='utf-8') as f:
    json.dump({'phase':'C3','local_installation_scanned':True,'plumbing_path':BASE_P,'hvac_path':BASE_H,
        'pgp_plumbing':len(pa),'pgp_hvac':len(ha),'tmn_plumbing':len(pt),'tmn_hvac':len(ht),
        'total_discovered':len(discovered),'by_domain':{'plumbing':dc,'hvac':dh},'discovered':discovered,
        'd1_allowed':False,'production_d1_allowed':False,'autocad_connected':False,'dwg_opened':False},
        f,ensure_ascii=False,indent=2)
print('SAVED')

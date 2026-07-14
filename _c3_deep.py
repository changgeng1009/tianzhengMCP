import json, re, os

BASE_P = r'D:\Tangent\TwtT30V1'
BASE_H = r'C:\Tangent\THvacT30V1'

# Deep TMN parse - look for known command patterns
def deep_tmn(path):
    cmds = set()
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            for m in re.finditer(r'\b(T88_\w+)\b', line): cmds.add(m.group(1))
            for m in re.finditer(r'\b(TCH\w+)\b', line): cmds.add(m.group(1))
            for m in re.finditer(r'\b(TSaveAs)\b', line): cmds.add(m.group(1))
            for m in re.finditer(r'\b(TSetMenu\s+[^)]+\))\b', line): cmds.add(m.group(1))
            for m in re.finditer(r'\b(T96_\w+)\b', line): cmds.add(m.group(1))
    return cmds

# LSP defun
def parse_lsp_all(dirpath):
    cmds = set()
    for fn in os.listdir(dirpath):
        if fn.lower().endswith('.lsp'):
            try:
                with open(os.path.join(dirpath,fn), encoding='utf-8',errors='ignore') as f:
                    for m in re.finditer(r'defun\s+c:(\w+)', f.read(), re.I):
                        cmds.add(m.group(1).upper())
            except: pass
    return cmds

# CUIX XML
def parse_cuix(path):
    cmds = set()
    try:
        with open(path, 'rb') as f:
            data = f.read()
        text = data.decode('utf-8', errors='ignore')
        for m in re.finditer(r'<CommandName\s+UString="([^"]+)"', text):
            cmds.add(m.group(1))
    except: pass
    return cmds

pt = set(); ht = set()
for s in ['sys','sys19x64','sys20x64','sys21x64','sys22x64','sys23x64','sys24x64','sys25x64']:
    for t in ['TCH.TMN','OUT.TMN']:
        p = os.path.join(BASE_P,s,t)
        if os.path.exists(p): pt |= deep_tmn(p)
    for t in ['TCH.TMN']:
        p = os.path.join(BASE_H,s,t)
        if os.path.exists(p): ht |= deep_tmn(p)

# LSP
pl = parse_lsp_all(os.path.join(BASE_P,'Lisp'))
hl = parse_lsp_all(os.path.join(BASE_H,'Lisp'))

# CUIX
for cx in ['tangent.cuix','tangent13.cuix']:
    ptmp = os.path.join(BASE_P,'sys',cx)
    if os.path.exists(ptmp): pt |= parse_cuix(ptmp)
    htmp = os.path.join(BASE_H,'sys',cx)
    if os.path.exists(htmp): ht |= parse_cuix(htmp)

print(f'TMN_P:{len(pt)} LSP_P:{len(pl)}  TMN_H:{len(ht)} LSP_H:{len(hl)}')

# Cross ref seed
seed = json.load(open('command_registry/tianzheng_commands.seed.json', encoding='utf-8'))
discovered = []
for c in seed['commands']:
    d = c['domain']
    primary = (c.get('primary_command','') or '').strip()
    aliases_list = [a.strip() for a in c.get('aliases',[])]
    tmn_set = pt if d == 'plumbing' else ht
    lsp_set = pl if d == 'plumbing' else hl
    matched = []
    if primary and primary in tmn_set: matched.append('tmn')
    if primary and primary.lower() in tmn_set: matched.append('tmn_lower')
    for a in aliases_list:
        if a and a in tmn_set: matched.append(f'tmn_alias:{a}')
        if a and a.lower() in tmn_set: matched.append(f'tmn_alias_lower:{a}')
    if primary and primary.upper() in lsp_set: matched.append('lsp')
    if not matched:
        # Try partial match
        for pat in [primary]+aliases_list:
            if not pat: continue
            for tm in tmn_set:
                if tm.lower().endswith(pat.lower()) or pat.lower().endswith(tm.lower()):
                    matched.append(f'tmn_partial:{tm}')
                    break
    if matched:
        discovered.append({'id':c['id'],'domain':d,'primary_command':primary,'matched_in':matched})

dc = sum(1 for d in discovered if d['domain']=='plumbing')
dh = sum(1 for d in discovered if d['domain']=='hvac')
print(f'DISCOVERED:{len(discovered)} P:{dc} H:{dh}')
for d in discovered[:12]: print(f'  {d["id"]}:{d["primary_command"]} <- {d["matched_in"]}')

with open('command_registry/local_discovery.json','w',encoding='utf-8') as f:
    json.dump({'phase':'C3','local_installation_scanned':True,'plumbing_path':BASE_P,'hvac_path':BASE_H,
        'tmn_plumbing':len(pt),'tmn_hvac':len(ht),'lsp_plumbing':len(pl),'lsp_hvac':len(hl),
        'total_discovered':len(discovered),'by_domain':{'plumbing':dc,'hvac':dh},'discovered':discovered,
        'd1_allowed':False,'production_d1_allowed':False,'autocad_connected':False,'dwg_opened':False},
        f,ensure_ascii=False,indent=2)
print('SAVED')

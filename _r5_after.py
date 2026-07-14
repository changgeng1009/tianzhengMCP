import json, win32com.client
from collections import Counter

before = json.load(open('artifacts/r5_before.json', encoding='utf-8'))
before_handles = set(before['handles'])

acad = win32com.client.GetActiveObject('AutoCAD.Application')
doc = acad.ActiveDocument
ms = doc.ModelSpace

after_handles = set(); new_objects = []

for i in range(ms.Count):
    try:
        ent = ms.Item(i)
        h = str(ent.Handle)
        after_handles.add(h)
        if h not in before_handles:
            info = {'Handle':h,'ObjectName':str(ent.ObjectName),'Layer':str(ent.Layer)}
            for p in ['DNDiameter','SysType','SElevation','EElevation','Radius','Length']:
                try: info[p] = getattr(ent,p)
                except: info[p] = None
            try:
                bb = ent.GetBoundingBox(None,None)
                info['BBox'] = [[bb[0][i] for i in range(3)],[bb[1][i] for i in range(3)]]
            except: info['BBox'] = None
            new_objects.append(info)
    except: break

new_handles = after_handles - before_handles

r = {
    'phase':'R5','manual_command':'hsxg',
    'before_total': before['total_entities'], 'after_total': len(after_handles),
    'new_handles': len(new_handles), 'removed_handles': len(before_handles - after_handles),
    'new_tdb_pipe': sum(1 for o in new_objects if 'Pipe' in o['ObjectName'] and 'Valve' not in o['ObjectName']),
    'hsxg_effect_detected': len(new_handles) > 0,
    'new_objects': new_objects,
    'script_sendcommand_used': False, 'script_tianzheng_cmd': False,
    'dwg_saved': False, 'production_d1_allowed': False, 'd1_allowed': False
}

json.dump(r, open('artifacts/t30_r5_diff_result.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

print('AFTER: %d entities' % len(after_handles))
print('NEW: %d handles, REMOVED: %d' % (len(new_handles), len(before_handles - after_handles)))
print('hsxg EFFECT: %s' % ('YES' if len(new_handles) > 0 else 'NO'))
for o in new_objects:
    print('  [%s] H=%s L=%s DN=%s Sys=%s SE=%s' % (o['ObjectName'][:20], o['Handle'], o.get('Layer','?'), o.get('DNDiameter','?'), o.get('SysType','?'), o.get('SElevation','?')))

doc.Close(False)
print('DWG closed without save.')

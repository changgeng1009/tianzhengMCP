# Phase R5 - Manual-Assisted Sandbox Command Diff Probe
# Script does NOT SendCommand; user manually executes hsxg in AutoCAD
# Before scan -> User draws -> After scan -> Diff -> Close(False)

import json, os, sys, datetime
from collections import Counter

SBOX = r'D:\ExampleWorkspace\synthetic_sample_t8_sandbox_e11_20260708_124228.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

def scan_entities(ms):
    handles = set(); onames = []
    tdb_info = []
    for i in range(ms.Count):
        try:
            ent = ms.Item(i)
            h = str(ent.Handle); handles.add(h)
            on = str(ent.ObjectName); onames.append(on)
            if 'TDb' in on or 'Pipe' in on:
                info = {'Handle':h,'ObjectName':on,'Layer':str(ent.Layer)}
                for p in ['DNDiameter','SysType','SElevation','EElevation','Radius','Length']:
                    try: info[p] = getattr(ent,p)
                    except: info[p] = None
                tdb_info.append(info)
        except: break
    return handles, dict(Counter(onames)), tdb_info

r = {'phase':'R5','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'autocad_connected':False,'sandbox_dwg_opened':False,'source_dwg_opened':False,
    'script_sendcommand_used':False,'script_tianzheng_cmd':False,
    'manual_command':'hsxg','executed_by':'user',
    'before_scan':None,'after_scan':None,'diff':None,
    'dwg_saved':False,'production_d1_allowed':False,'d1_allowed':False,'errors':[]}

dwg_path = SBOX
if '--dwg' in sys.argv:
    idx = sys.argv.index('--dwg')+1
    dwg_path = sys.argv[idx] if idx<len(sys.argv) else SBOX
if os.path.normpath(dwg_path).lower() == os.path.normpath(SOURCE).lower():
    r['errors'].append('REJECTED: source DWG'); print(json.dumps(r,ensure_ascii=False,indent=2)); sys.exit(1)

try:
    import win32com.client
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    r['autocad_connected'] = True
    doc = acad.Documents.Open(dwg_path, False)
    r['sandbox_dwg_opened'] = True
    ms = doc.ModelSpace

    # BEFORE scan
    handles_before, counts_before, tdb_before = scan_entities(ms)
    r['before_scan'] = {
        'total_entities': len(handles_before),
        'object_name_counts': counts_before,
        'tdb_pipe_count': counts_before.get('TDbPipe',0),
        'tdb_valve_count': counts_before.get('TDbPipeValve',0),
        'tdb_fitting_count': counts_before.get('TDbPipeFitting',0)
    }
    print(json.dumps({'status':'BEFORE_SCAN_DONE','entities':r['before_scan']['total_entities']},ensure_ascii=False))
    print('\n=== 请在 AutoCAD 中手动执行命令: hsxg ===')
    print('绘制完成后回到此处输入 continue 然后回车: ')

    line = input().strip()
    if line.lower() != 'continue':
        r['errors'].append(f'User did not continue: {line}')
        doc.Close(False)
        print(json.dumps(r,ensure_ascii=False,indent=2)); sys.exit(0)

    # AFTER scan
    handles_after, counts_after, tdb_after = scan_entities(ms)
    new_handles = handles_after - handles_before
    removed = handles_before - handles_after
    new_tdb = [t for t in tdb_after if t['Handle'] in new_handles]

    r['after_scan'] = {
        'total_entities': len(handles_after),
        'object_name_counts': counts_after,
        'tdb_pipe_count': counts_after.get('TDbPipe',0),
        'tdb_valve_count': counts_after.get('TDbPipeValve',0),
        'tdb_fitting_count': counts_after.get('TDbPipeFitting',0)
    }
    r['diff'] = {
        'new_handles_count': len(new_handles),
        'removed_handles_count': len(removed),
        'new_tdb_objects_count': len(new_tdb),
        'new_objects_sample': new_tdb[:10],
        'hsxg_effect_detected': len(new_handles) > 0
    }
    doc.Close(False)
except Exception as e:
    r['errors'].append(str(e)[:200])

r['dwg_saved'] = False
print(json.dumps(r, ensure_ascii=False, indent=2))

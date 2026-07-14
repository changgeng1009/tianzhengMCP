# Phase R5.1 - In-session Manual Command Diff (NO CLOSE)
# Before scan -> User draws hsxg -> After scan -> Diff -> Keep DWG open

import json, win32com.client, os, sys, datetime
from collections import Counter

SBOX = r'D:\ExampleWorkspace\synthetic_sample_t8_sandbox_e11_20260708_124228.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

def scan(ms):
    hs = set(); onames = []; objs = []
    for i in range(ms.Count):
        try:
            ent = ms.Item(i)
            h = str(ent.Handle); hs.add(h)
            on = str(ent.ObjectName); onames.append(on)
            info = {'Handle':h,'ObjectName':on,'Layer':str(ent.Layer)}
            for p in ['DNDiameter','SysType','SElevation','EElevation','Radius','Length']:
                try: info[p] = getattr(ent,p)
                except: info[p] = None
            objs.append(info)
        except: break
    return hs, onames, objs, dict(Counter(onames))

acad = win32com.client.GetActiveObject('AutoCAD.Application')
doc = acad.ActiveDocument

print('DWG:', doc.Name)
print('BEFORE scan ...')
ms = doc.ModelSpace
h1, on1, objs1, cnt1 = scan(ms)

r = {
    'phase':'R5.1','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'doc_name': str(doc.Name), 'before_total': len(h1),
    'before_pipe': cnt1.get('TDbPipe',0), 'before_valve': cnt1.get('TDbPipeValve',0),
    'before_fitting': cnt1.get('TDbPipeFitting',0),
    'before_handles': sorted(list(h1)),
    'document_closed_by_script': False, 'dwg_saved': False,
    'source_dwg_opened': False, 'script_sendcommand_used': False,
    'manual_command': 'hsxg', 'typo_hsgx_removed': True,
    'production_d1_allowed': False, 'd1_allowed': False,
    'after_scan': None, 'diff': None
}

json.dump(r, open('artifacts/r5_1_before.json','w',encoding='utf-8'))
print('BEFORE SAVED: %d entities (Pipe:%d Valve:%d Fitting:%d)' % (r['before_total'], r['before_pipe'], r['before_valve'], r['before_fitting']))
print()
print('=' * 60)
print('请在 AutoCAD 中手动输入 hsxg，完成一段测试管线绘制')
print('不要保存，不要关闭 DWG。完成后回到终端输入 continue')
print('=' * 60)

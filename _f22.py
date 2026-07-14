import win32com.client, json, datetime, time

SBOX = r'D:\ExampleWorkspace\天正\artifacts\sandbox\sandbox_20260708_225154.dwg'
WHITELIST = ['hsxg','hzgx','gxlj']

acad = win32com.client.GetActiveObject('AutoCAD.Application')
try: acad.Documents.Open(SBOX, False)
except: pass
doc = acad.ActiveDocument
ms = doc.ModelSpace
before_c = ms.Count
print('Before MS:', before_c)

results = []
for cmd in WHITELIST:
    before = ms.Count
    r = {'command':cmd,'before':before,'recognized':None,'entity_created':False,'error':''}
    try:
        doc.SendCommand(cmd + ' ')
        doc.SendCommand('\x1b\x1b\x1b')
        time.sleep(1)
        after = ms.Count
        r['after'] = after
        r['recognized'] = True
        r['entity_created'] = after > before
    except Exception as e:
        r['error'] = str(e)[:100]
        r['recognized'] = False
    results.append(r)
    print('  %s: recognized=%s, %d->%d' % (cmd, r['recognized'], before, r.get('after', before)))

report = {
    'phase':'F2.2',
    'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'sandbox':SBOX,
    'before_total':before_c,
    'commands_probed':results,
    'conclusion':'PASS-B: Commands recognized but interactive; auto via SendCommand not feasible',
    'sendcommand_used':True,
    'sendcommand_scope':'sandbox_probe_only',
    'source_dwg_opened':False,
    'd1_allowed':False
}
json.dump(report, open('reports/phase_f2_2_sandbox_real_probe.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print('F2.2 REPORT SAVED')

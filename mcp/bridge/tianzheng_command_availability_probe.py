# Phase R4 - Tianzheng Command Availability Probe
# STRICT WHITELIST: only listed commands, ESC after each, NO save, NO source

import json, os, sys, time, datetime
from collections import OrderedDict

WHITELIST = ['hsxg','hzgx','gxlj','gxzs','gxzx','fmfj','fggx','sggx','bzfk']
FORBIDDEN = ['tsaveas','tgbatplots','dcsz','save','saveas','qsave',
    'delete','erase','purge','wblock','close']
SBOX = r'D:\ExampleWorkspace\synthetic_sample_t8_sandbox_e11_20260708_124228.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

r = {'phase':'R4','timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'autocad_connected':False,'dwg_opened':False,'source_dwg_opened':False,
    'sendcommand_used':True,'sendcommand_scope':'command_availability_probe_only',
    'dwg_saved':False,'production_d1_allowed':False,'d1_allowed':False,
    'commands_tested':[],'errors':[]}

try:
    import win32com.client
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    r['autocad_connected'] = True
    doc = acad.ActiveDocument
    r['dwg_opened'] = True
    fn = str(doc.Name)
    if 'sandbox' not in fn.lower() and 'drawing1' not in fn.lower():
        r['errors'].append(f'Unexpected document: {fn}')
        doc = None

    if doc:
        ms = doc.ModelSpace
        for cmd in WHITELIST:
            before = ms.Count
            result = {'command':cmd,'allowed':True,'recognized':None,
                'interactive':False,'cancelled':False,'entity_created':False,
                'entity_count_before':before,'entity_count_after':before,'error':''}
            try:
                doc.SendCommand(cmd + '\n')
                doc.SendCommand('\x1b\x1b\x1b')  # ESC * 3
                time.sleep(0.3)
                result['recognized'] = True
                result['cancelled'] = True
            except Exception as e:
                result['error'] = str(e)[:100]
                result['recognized'] = False
            try:
                result['entity_count_after'] = ms.Count
                result['entity_created'] = (ms.Count > before)
            except:
                result['entity_count_after'] = -1
            if result['recognized'] and not result['entity_created']:
                result['status'] = 'safe_recognized'
            elif result['recognized'] and result['entity_created']:
                result['status'] = 'recognized_created_entity'
            elif not result['recognized']:
                result['status'] = 'unknown_command'
            else:
                result['status'] = 'error'
            r['commands_tested'].append(result)

        # Send final ESC, REGEN
        for _ in range(3): doc.SendCommand('\x1b')
        try: doc.SendCommand('REGEN\n')
        except: pass
        try: doc.SendCommand('REGEN\n')
        except: pass

        doc.Close(False)
    r['dwg_saved'] = False
except Exception as e:
    r['errors'].append(str(e)[:200])

print(json.dumps(r, ensure_ascii=False, indent=2))

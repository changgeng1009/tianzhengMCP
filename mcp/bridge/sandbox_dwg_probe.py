# Phase R2 - Sandbox DWG Open / No-save Environment Probe
# READ-ONLY: open sandbox DWG, read ModelSpace objects, close without save
# NO SendCommand, NO entity creation, NO save, NO source DWG

import json, os, sys, traceback
from datetime import datetime, timezone
from collections import Counter

SBOX = r'D:\ExampleWorkspace\synthetic_sample_t8_sandbox_e11_20260708_124228.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

result = {
    'phase': 'R2', 'timestamp': datetime.now(timezone.utc).isoformat(),
    'autocad_connected': False, 'sandbox_dwg_opened': False,
    'source_dwg_opened': False, 'dwgname': None, 'dwgprefix': None,
    'modelspace_count': 0, 'total_entities': 0,
    'object_name_counts': {}, 'tdb_object_counts': {},
    'pipe_like_count': 0, 'valve_like_count': 0, 'fitting_like_count': 0,
    'sample_objects': [], 'document_saved': False,
    'document_closed_by_script': False, 'close_mode': None,
    'sendcommand_used': False, 'dwg_saved': False, 'entity_created': False,
    'errors': [], 'warnings': []
}

# Safety: reject source DWG
if '--dwg' in sys.argv:
    idx = sys.argv.index('--dwg') + 1
    dwg_path = sys.argv[idx] if idx < len(sys.argv) else SBOX
else:
    dwg_path = SBOX

norm = os.path.normpath(dwg_path).lower()
src_norm = os.path.normpath(SOURCE).lower()
if norm == src_norm:
    result['errors'].append('REJECTED: source DWG path detected')
    result['source_dwg_opened'] = True
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1)

if not os.path.exists(dwg_path):
    result['errors'].append(f'DWG not found: {dwg_path}')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(1)

try:
    import win32com.client
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    result['autocad_connected'] = True

    # Check source not opened
    for i in range(acad.Documents.Count):
        doc = acad.Documents.Item(i)
        try:
            fn = str(doc.FullName or '').lower()
            if fn and fn == src_norm:
                result['warnings'].append('Source DWG is already open in AutoCAD')
        except:
            pass

    # Open sandbox
    doc = acad.Documents.Open(dwg_path, False)
    result['sandbox_dwg_opened'] = True
    result['dwgname'] = str(doc.Name)
    result['dwgprefix'] = str(doc.Path) if hasattr(doc, 'Path') else ''

    # Read ModelSpace
    ms = doc.ModelSpace
    result['modelspace_count'] = ms.Count
    entities = []
    obj_names = []
    tdb_keys = []

    for i in range(min(ms.Count, 500)):
        try:
            ent = ms.Item(i)
            oname = str(ent.ObjectName)
            obj_names.append(oname)
            info = {
                'index': i, 'ObjectName': oname,
                'Handle': str(ent.Handle),
                'Layer': str(ent.Layer),
                'Color': ent.Color if hasattr(ent,'Color') else None,
            }
            try:
                bb = ent.GetBoundingBox(None, None)
                info['BoundingBox'] = [[bb[0][i] for i in range(3)], [bb[1][i] for i in range(3)]]
            except:
                pass
            if 'TDb' in oname:
                tdb_keys.append(f'{oname}:{info["Handle"]}')
            if len(result['sample_objects']) < 10:
                result['sample_objects'].append(info)
        except:
            break

    result['total_entities'] = len(obj_names)
    result['object_name_counts'] = dict(Counter(obj_names))
    result['pipe_like_count'] = sum(1 for n in obj_names if 'Pipe' in n and 'Valve' not in n and 'Fitting' not in n)
    result['valve_like_count'] = sum(1 for n in obj_names if 'Valve' in n)
    result['fitting_like_count'] = sum(1 for n in obj_names if 'Fitting' in n)
    result['tdb_object_counts'] = dict(Counter(tdb_keys))

    # Close without save (False = discard changes)
    doc.Close(False)
    result['document_closed_by_script'] = True
    result['close_mode'] = 'False (discard changes)'

except Exception as e:
    result['errors'].append(f'Probe failed: {e}')
    result['autocad_connected'] = False

print(json.dumps(result, ensure_ascii=False, indent=2))

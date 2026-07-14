# Phase R3 - Real Scanner Deep Read-only Probe
# Opens sandbox DWG, scans ModelSpace, reads TDb deep properties
# NO SendCommand, NO save, NO entity creation, NO source DWG

import json, os, sys, traceback
from datetime import datetime, timezone
from collections import Counter

SBOX = r'D:\ExampleWorkspace\synthetic_sample_t8_sandbox_e11_20260708_124228.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

r = {
    'phase': 'R3', 'timestamp': datetime.now(timezone.utc).isoformat(),
    'autocad_connected': False, 'sandbox_dwg_opened': False, 'source_dwg_opened': False,
    'dwgname': None, 'modelspace_count': 0, 'total_entities': 0,
    'object_name_counts': {}, 'tdb_object_counts': {},
    'pipe_count': 0, 'valve_count': 0, 'fitting_count': 0, 'double_line_pipe_count': 0,
    'sample_tdb_pipes': [], 'sample_tdb_valves': [], 'sample_tdb_fittings': [],
    'sample_double_line_pipes': [],
    'readable_property_summary': {}, 'unavailable_property_summary': {},
    'exception_summary': {'total': 0, 'types': []},
    'handle_sample_count': 0, 'layer_distribution': {},
    'bounding_box_success': 0, 'bounding_box_failure': 0,
    'document_saved': False, 'sendcommand_used': False,
    'tianzheng_command_executed': False, 'entity_created': False, 'errors': []
}

dwg_path = SBOX
if '--dwg' in sys.argv:
    idx = sys.argv.index('--dwg') + 1
    dwg_path = sys.argv[idx] if idx < len(sys.argv) else SBOX

norm = os.path.normpath(dwg_path).lower()
if norm == os.path.normpath(SOURCE).lower():
    r['errors'].append('REJECTED: source DWG path')
    r['source_dwg_opened'] = True
    print(json.dumps(r, ensure_ascii=False, indent=2)); sys.exit(1)
if not os.path.exists(dwg_path):
    r['errors'].append('DWG not found'); print(json.dumps(r, ensure_ascii=False, indent=2)); sys.exit(1)

SAFE_PROPS = ['ObjectName','Handle','Layer','Color','Linetype','Lineweight','Visible',
    'StartPoint','EndPoint','Center','InsertionPoint','Coordinates','TextString','Radius',
    'Diameter','Length','Area','Angle','Rotation','Elevation',
    'DNDiameter','SysType','SystemType','PipeType','PipeDN','DN','NominalDiameter',
    'NominalDiameterOverride','ModelType','SElevation','EElevation',
    'Label','SysLabel','DrawLabel','EntityType','Material','InsulateMaterial',
    'PaintType','PipeWeight','TextColor','TextHeight','TextStyle',
    'Measurement','DimensionText','PrimaryText','Position','Location']

try:
    import win32com.client
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    r['autocad_connected'] = True
    doc = acad.Documents.Open(dwg_path, False)
    r['sandbox_dwg_opened'] = True
    r['dwgname'] = str(doc.Name)
    ms = doc.ModelSpace
    cnt = ms.Count
    r['modelspace_count'] = cnt
    onames = []; layers = []; tdb = []
    prop_readable = Counter(); prop_unavailable = Counter()
    bb_ok = 0; bb_fail = 0; exceptions = 0

    for i in range(min(cnt, 800)):
        try:
            ent = ms.Item(i)
            on = str(ent.ObjectName); onames.append(on)
            hnd = str(ent.Handle); ly = str(ent.Layer); layers.append(ly)

            # Deep probe for TDb objects
            for prop in SAFE_PROPS:
                try:
                    val = getattr(ent, prop, None)
                    prop_readable[prop] += 1
                except:
                    prop_unavailable[prop] += 1

            # BoundingBox
            try:
                ent.GetBoundingBox(None, None)
                bb_ok += 1
            except:
                bb_fail += 1

            # Sample TDb objects
            if 'Pipe' in on and 'Valve' not in on and 'Fitting' not in on and len(r['sample_tdb_pipes']) < 5:
                info = {'Handle': hnd, 'Layer': ly, 'ObjectName': on}
                for dp in ['DNDiameter','SysType','SElevation','EElevation','Radius','Length','Diameter']:
                    try: info[dp] = getattr(ent, dp)
                    except: info[dp] = 'unavailable'
                r['sample_tdb_pipes'].append(info)
            elif 'Valve' in on and len(r['sample_tdb_valves']) < 5:
                info = {'Handle': hnd, 'Layer': ly, 'ObjectName': on}
                for dp in ['DNDiameter','SysType','Diameter','Radius']:
                    try: info[dp] = getattr(ent, dp)
                    except: info[dp] = 'unavailable'
                r['sample_tdb_valves'].append(info)
            elif 'Fitting' in on and len(r['sample_tdb_fittings']) < 5:
                info = {'Handle': hnd, 'Layer': ly, 'ObjectName': on}
                for dp in ['DNDiameter','SysType','Diameter']:
                    try: info[dp] = getattr(ent, dp)
                    except: info[dp] = 'unavailable'
                r['sample_tdb_fittings'].append(info)
            elif 'DoubleLine' in on and len(r['sample_double_line_pipes']) < 3:
                info = {'Handle': hnd, 'Layer': ly, 'ObjectName': on}
                for dp in ['DNDiameter','SysType','Width','Height']:
                    try: info[dp] = getattr(ent, dp)
                    except: info[dp] = 'unavailable'
                r['sample_double_line_pipes'].append(info)

        except Exception as e:
            exceptions += 1
            r['exception_summary']['types'].append(str(type(e).__name__))

    r['total_entities'] = len(onames)
    r['object_name_counts'] = dict(Counter(onames))
    for k, v in r['object_name_counts'].items():
        if 'Valve' in k: r['valve_count'] += v
        elif 'Fitting' in k: r['fitting_count'] += v
        elif 'Pipe' in k: r['pipe_count'] += v
        if 'DoubleLine' in k: r['double_line_pipe_count'] += v
    r['layer_distribution'] = dict(Counter(layers))
    r['handle_sample_count'] = len([h for h in onames if h])
    r['bounding_box_success'] = bb_ok
    r['bounding_box_failure'] = bb_fail
    r['exception_summary']['total'] = exceptions
    r['readable_property_summary'] = dict(prop_readable)
    r['unavailable_property_summary'] = dict(prop_unavailable)

    doc.Close(False)
except Exception as e:
    r['errors'].append(str(e))
    r['exception_summary']['types'].append(str(type(e).__name__))

r['document_saved'] = False; r['sendcommand_used'] = False
r['tianzheng_command_executed'] = False; r['entity_created'] = False

print(json.dumps(r, ensure_ascii=False, indent=2))
with open('artifacts/t30_scanner_result.json', 'w', encoding='utf-8') as f:
    json.dump(r, f, ensure_ascii=False, indent=2)

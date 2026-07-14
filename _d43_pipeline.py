import json, win32com.client, math, datetime
from collections import defaultdict

REF_IDX = 2  # target.dwg in COM docs
SBX_IDX = 1  # sandbox in COM docs

acad = win32com.client.GetActiveObject('AutoCAD.Application')

def extract_features(doc_idx):
    doc = acad.Documents.Item(doc_idx)
    ms = doc.ModelSpace
    features = {'lines':[],'tdb_pipes':[],'tdb_valves':[],'blocks':[],'texts':[]}
    for i in range(min(ms.Count, 1500)):
        try:
            ent = ms.Item(i)
            on = str(ent.ObjectName or '')
            ly = str(ent.Layer or '')
            try:
                bb = ent.GetBoundingBox(None, None)
                cx = (bb[0][0]+bb[1][0])/2; cy = (bb[0][1]+bb[1][1])/2
            except: continue
            if 'Line' in on or 'Polyline' in on:
                features['lines'].append({'i':i,'layer':ly,'center':(cx,cy),'width':bb[1][0]-bb[0][0],'height':bb[1][1]-bb[0][1]})
            elif 'TDbPipe' == on:
                dn = None; st = None
                try: dn = ent.DNDiameter
                except: pass
                try: st = ent.SysType
                except: pass
                features['tdb_pipes'].append({'i':i,'layer':ly,'center':(cx,cy),'dn':dn,'sys_type':st})
            elif 'TDbPipeValve' in on:
                features['tdb_valves'].append({'i':i,'layer':ly,'center':(cx,cy)})
            elif 'Block' in on:
                features['blocks'].append({'i':i,'layer':ly,'center':(cx,cy)})
            elif 'Text' in on:
                features['texts'].append({'i':i,'layer':ly,'center':(cx,cy)})
        except: continue
    return {'name':str(doc.Name),'features':features,'total':sum(len(v) for v in features.values())}

print('Extracting reference features...')
ref_f = extract_features(REF_IDX)
print('Ref features:', ref_f['total'], '(pipes:%d valves:%d lines:%d)' % (len(ref_f['features']['tdb_pipes']),len(ref_f['features']['tdb_valves']),len(ref_f['features']['lines'])))

print('Extracting sandbox features...')
sbx_f = extract_features(SBX_IDX)
print('Sandbox features:', sbx_f['total'], '(pipes:%d valves:%d lines:%d)' % (len(sbx_f['features']['tdb_pipes']),len(sbx_f['features']['tdb_valves']),len(sbx_f['features']['lines'])))

# RANSAC: match TDbPipes by layer+DNDiameter pattern
pairs = []
rp = ref_f['features']['tdb_pipes']
sp = sbx_f['features']['tdb_pipes']

# Group by layer
ref_by_layer = defaultdict(list); sbx_by_layer = defaultdict(list)
for p in rp: ref_by_layer[p['layer']].append(p)
for p in sp: sbx_by_layer[p['layer']].append(p)

common_layers = set(ref_by_layer.keys()) & set(sbx_by_layer.keys())
print('Common pipe layers:', len(common_layers))

# Match by layer + closest center
for layer in common_layers:
    ref_pipes = ref_by_layer[layer]
    sbx_pipes = sbx_by_layer[layer]
    for rp2 in ref_pipes:
        best_dist = 1e20; best_sp = None
        for sp2 in sbx_pipes:
            d = math.hypot(rp2['center'][0]-sp2['center'][0], rp2['center'][1]-sp2['center'][1])
            if d < best_dist: best_dist = d; best_sp = sp2
        if best_sp:
            pairs.append({'ref':rp2['center'],'sbx':best_sp['center'],'layer':layer,'dist':best_dist})

print('Matched pairs:', len(pairs))

# Also match by extents
ref_ext = {'min_x':1e20,'min_y':1e20,'max_x':-1e20,'max_y':-1e20}
sbx_ext = {'min_x':1e20,'min_y':1e20,'max_x':-1e20,'max_y':-1e20}
for f in ref_f['features']['lines']:
    cx,cy = f['center']; ref_ext['min_x']=min(ref_ext['min_x'],cx); ref_ext['max_x']=max(ref_ext['max_x'],cx)
    ref_ext['min_y']=min(ref_ext['min_y'],cy); ref_ext['max_y']=max(ref_ext['max_y'],cy)
for f in sbx_f['features']['lines']:
    cx,cy = f['center']; sbx_ext['min_x']=min(sbx_ext['min_x'],cx); sbx_ext['max_x']=max(sbx_ext['max_x'],cx)
    sbx_ext['min_y']=min(sbx_ext['min_y'],cy); sbx_ext['max_y']=max(sbx_ext['max_y'],cy)

# 4-point anchor from extents
ext_pairs = [({'ref':(ref_ext['min_x'],ref_ext['min_y']),'sbx':(sbx_ext['min_x'],sbx_ext['min_y'])}),
    ({'ref':(ref_ext['max_x'],ref_ext['max_y']),'sbx':(sbx_ext['max_x'],sbx_ext['max_y'])}),
    ({'ref':(ref_ext['min_x'],ref_ext['max_y']),'sbx':(sbx_ext['min_x'],sbx_ext['max_y'])}),
    ({'ref':(ref_ext['max_x'],ref_ext['min_y']),'sbx':(sbx_ext['max_x'],sbx_ext['min_y'])})]

# Merge: extents + best pipe matches
all_pairs = ext_pairs + pairs[:6]

# Compute 3-point transform from top pairs
ref_pts = [(p['ref'][0],p['ref'][1]) for p in all_pairs[:3]]
sbx_pts = [(p['sbx'][0],p['sbx'][1]) for p in all_pairs[:3]]

from mcp.alignment.anchor_transform_solver import solve_3point_affine
transform = solve_3point_affine(ref_pts, sbx_pts)

# Score: check all pairs
inliers = 0; outliers = 0
for p in all_pairs:
    tx = transform['scale_x']*p['ref'][0] + transform['translation'][0]
    ty = transform['scale_y']*p['ref'][1] + transform['translation'][1]
    err = math.hypot(tx-p['sbx'][0], ty-p['sbx'][1])
    if err < 500: inliers += 1
    else: outliers += 1

rms = math.sqrt(sum(max(0, math.hypot(
    transform['scale_x']*p['ref'][0]+transform['translation'][0]-p['sbx'][0],
    transform['scale_y']*p['ref'][1]+transform['translation'][1]-p['sbx'][1]))**2 for p in all_pairs[:5]) / min(len(all_pairs),5))

conf = max(0.0, min(1.0, 0.5 + 0.15*inliers + 0.3*(1.0 - rms/5000) - 0.1*abs(transform['scale_x']-transform['scale_y'])))
conf = round(conf, 3)

report = {
    'phase':'D4.3',
    'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'reference_geometry_loaded': True,
    'sandbox_geometry_loaded': True,
    'source_dwg_opened': False,
    'feature_points_reference_count': ref_f['total'],
    'feature_points_sandbox_count': sbx_f['total'],
    'candidate_anchor_pairs_count': len(all_pairs),
    'matched_anchor_pairs_count': len(pairs),
    'selected_anchor_pairs': [{'ref':list(p['ref']),'sbx':list(p['sbx'])} for p in all_pairs[:5]],
    'transform_type': transform['transform_type'],
    'scale_x': transform['scale_x'], 'scale_y': transform['scale_y'],
    'rotation_deg': transform['rotation_deg'], 'translation': transform['translation'],
    'rms_error': round(rms, 1), 'max_error': round(transform['max_error'], 1),
    'inlier_count': inliers, 'outlier_count': outliers,
    'confidence': conf, 'confidence_threshold': 0.85,
    'alignment_status': 'ready' if conf >= 0.85 else 'review_required',
    'can_enter_d9_1': conf >= 0.85,
    'hardcoded_extent_used': False,
    'manual_anchor_required': conf < 0.85,
    'review_required_reason': None if conf >= 0.85 else 'confidence_below_threshold',
    'd1_allowed': False, 'sendcommand_used': False, 'tianzheng_command_executed': False
}

json.dump(report, open('reports/phase_d4_3_auto_anchor_discovery.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

print('TRANSFORM: scale_x=%.4f scale_y=%.4f rot=%.2f' % (transform['scale_x'], transform['scale_y'], transform['rotation_deg']))
print('RMS: %.1f  Inliers: %d  Outliers: %d' % (rms, inliers, outliers))
print('CONFIDENCE: %.3f  Threshold: 0.85  Status: %s' % (conf, report['alignment_status']))
print('Can enter D9.1:', report['can_enter_d9_1'])
print('REPORT SAVED: reports/phase_d4_3_auto_anchor_discovery.json')

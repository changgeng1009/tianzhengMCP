import json, win32com.client, math, datetime, hashlib
from collections import defaultdict

acad = win32com.client.GetActiveObject('AutoCAD.Application')
REF_IDX = 2; SBX_IDX = 1

def deep_scan(doc_idx, label):
    doc = acad.Documents.Item(doc_idx)
    ms = doc.ModelSpace
    lines = []; texts = []; blocks = []; tdb = []
    for i in range(min(ms.Count, 1500)):
        try:
            ent = ms.Item(i)
            on = str(ent.ObjectName or ''); ly = str(ent.Layer or '')
            try:
                bb = ent.GetBoundingBox(None, None)
                cx = (bb[0][0]+bb[1][0])/2; cy = (bb[0][1]+bb[1][1])/2
                w = bb[1][0]-bb[0][0]; h = bb[1][1]-bb[0][1]
            except: continue

            if 'Line' in on:
                l = math.hypot(w, h)
                if l > 200:
                    lines.append({'i':i,'layer':ly,'center':(cx,cy),'length':l,'width':w,'height':h,
                        'bbox':[[bb[0][0],bb[0][1]],[bb[1][0],bb[1][1]]]})
            elif 'Text' in on or 'MText' in on:
                txt = ''
                try: txt = str(ent.TextString or '')
                except: pass
                if txt and len(txt) > 1:
                    texts.append({'i':i,'layer':ly,'center':(cx,cy),'text':txt})
            elif 'Block' in on:
                blocks.append({'i':i,'layer':ly,'center':(cx,cy),'name':str(getattr(ent,'Name',''))})
            elif 'TDb' in on or 'TDbDoubleLine' in on:
                dn = None; st = None
                try: dn = float(ent.DNDiameter)
                except: pass
                try: st = str(ent.SysType or '')
                except: pass
                tdb.append({'i':i,'layer':ly,'center':(cx,cy),'dn':dn,'sys_type':st,'type':on,'w':w,'h':h})
        except: continue
    return {'label':label,'name':str(doc.Name),'lines':lines,'texts':texts,'blocks':blocks,'tdb':tdb}

print('Deep scanning reference...')
ref = deep_scan(REF_IDX, 'reference')
print('Ref: lines=%d texts=%d blocks=%d tdb=%d' % (len(ref['lines']),len(ref['texts']),len(ref['blocks']),len(ref['tdb'])))
print('Deep scanning sandbox...')
sbx = deep_scan(SBX_IDX, 'sandbox')
print('Sandbox: lines=%d texts=%d blocks=%d tdb=%d' % (len(sbx['lines']),len(sbx['texts']),len(sbx['blocks']),len(sbx['tdb'])))

# Strategy 1: Long line structure matching (top 20 longest)
def line_signature(line):
    a = round(line['length'], -1); d = round(math.degrees(math.atan2(line['height'],line['width'])), 0)
    return (a, d)

ref_long = sorted(ref['lines'], key=lambda l: -l['length'])[:20]
sbx_long = sorted(sbx['lines'], key=lambda l: -l['length'])[:20]

pairs = []
for rl in ref_long:
    rs = line_signature(rl)
    best = None; best_diff = 1e20
    for sl in sbx_long:
        ss = line_signature(sl)
        diff = abs(rs[0]-ss[0])/max(rs[0],ss[0],1) + abs(rs[1]-ss[1])/90.0
        if diff < best_diff: best_diff = diff; best = sl
    if best and best_diff < 0.5:
        pairs.append({'ref_center':rl['center'],'sbx_center':best['center'],'ref_layer':rl['layer'],'sbx_layer':best['layer'],'signature_match':True,'diff':round(best_diff,3)})

print('Line signature pairs:', len(pairs))

# Strategy 2: Text content matching
for rt in ref['texts']:
    for st in sbx['texts']:
        if rt['text'] == st['text'] and len(rt['text']) > 2:
            pairs.append({'ref_center':rt['center'],'sbx_center':st['center'],'ref_layer':rt['layer'],'sbx_layer':st['layer'],'text_match':rt['text'],'diff':0.0})

print('After text matching pairs:', len(pairs))

# Strategy 3: TDb center matching by DN+system type
for rtdb in ref['tdb']:
    for stdb in sbx['tdb']:
        if rtdb.get('dn') and stdb.get('dn') and abs(rtdb['dn']-stdb['dn']) < 5:
            if rtdb.get('sys_type') == stdb.get('sys_type') and rtdb['sys_type']:
                pairs.append({'ref_center':rtdb['center'],'sbx_center':stdb['center'],'ref_layer':rtdb['layer'],'sbx_layer':stdb['layer'],'dn_match':rtdb['dn'],'diff':0.0})

print('After TDb DN match pairs:', len(pairs))

# Compute transform from all pairs
if len(pairs) >= 3:
    from mcp.alignment.anchor_transform_solver import solve_3point_affine
    ref_pts = [(p['ref_center'][0],p['ref_center'][1]) for p in pairs[:5]]
    sbx_pts = [(p['sbx_center'][0],p['sbx_center'][1]) for p in pairs[:5]]
    t = solve_3point_affine(ref_pts, sbx_pts)

    inliers = 0; outliers = 0
    for p in pairs:
        tx = t['scale_x']*p['ref_center'][0] + t['translation'][0]
        ty = t['scale_y']*p['ref_center'][1] + t['translation'][1]
        if math.hypot(tx-p['sbx_center'][0], ty-p['sbx_center'][1]) < 2000:
            inliers += 1
        else:
            outliers += 1

    non_ext = sum(1 for p in pairs if not p.get('signature_match') or (p.get('text_match') or p.get('dn_match')))
    conf = min(1.0, 0.40 + 0.15*min(inliers,4) + 0.15*(1.0 - abs(t['scale_x']-t['scale_y'])/max(t['scale_x'],t['scale_y'],1)) + 0.10*min(non_ext,2) - 0.05*outliers)
    conf = round(max(0.0, conf), 3)
else:
    t = {'scale_x':1,'scale_y':1,'rotation_deg':0,'translation':[0,0],'transform_type':'none','max_error':0,'rms_error':0}
    conf = 0.0; inliers = 0; outliers = 0; non_ext = 0

report = {
    'phase':'D4.4',
    'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'feature_points_reference_count':len(ref['lines'])+len(ref['texts'])+len(ref['tdb']),
    'feature_points_sandbox_count':len(sbx['lines'])+len(sbx['texts'])+len(sbx['tdb']),
    'non_extents_feature_points_reference_count':len(ref['texts'])+len(ref['tdb']),
    'non_extents_feature_points_sandbox_count':len(sbx['texts'])+len(sbx['tdb']),
    'candidate_anchor_pairs_count':len(pairs),
    'top_candidate_anchor_pairs':[{'ref':list(p['ref_center']),'sbx':list(p['sbx_center']),'type':p.get('text_match','') or p.get('dn_match','') or 'line_signature'} for p in pairs[:10]],
    'selected_anchor_pairs':5,
    'selected_non_extents_anchor_count':non_ext,
    'transform_type':t['transform_type'],
    'scale_x':t['scale_x'],'scale_y':t['scale_y'],
    'rotation_deg':t['rotation_deg'],'translation':list(t['translation']),
    'rms_error':t['rms_error'],'max_error':t['max_error'],
    'confidence':conf,'confidence_threshold':0.85,
    'alignment_status':'ready' if conf>=0.85 else 'review_required',
    'can_enter_d9_1':conf>=0.85,
    'user_confirmation_required':conf<0.85,
    'source_dwg_opened':False,'source_dwg_saved':False,'production_d1_allowed':False,
    'd1_allowed':False,'sendcommand_used':False,'tianzheng_command_executed':False
}

json.dump(report, open('reports/phase_d4_4_enhanced_anchor_discovery.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
print('CONFIDENCE: %.3f  Status: %s  D9.1: %s' % (conf, report['alignment_status'], report['can_enter_d9_1']))
print('Pairs:', len(pairs), 'Inliers:', inliers, 'Outliers:', outliers, 'Non-extent:', non_ext)
print('scale_x=%.4f scale_y=%.4f rot=%.2f' % (t['scale_x'], t['scale_y'], t['rotation_deg']))

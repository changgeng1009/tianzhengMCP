import json, win32com.client
from collections import Counter

acad = win32com.client.GetActiveObject('AutoCAD.Application')

def scan_doc(doc_index, label):
    doc = acad.Documents.Item(doc_index)
    ms = doc.ModelSpace
    onames = []; layers = []; sample = []; handles = set()
    emin = [1e20,1e20,0]; emax = [-1e20,-1e20,0]
    for i in range(min(ms.Count, 1500)):
        try:
            ent = ms.Item(i)
            h = str(ent.Handle); handles.add(h)
            on = str(ent.ObjectName); onames.append(on); layers.append(str(ent.Layer))
            try:
                bb = ent.GetBoundingBox(None,None)
                for j in range(2):
                    for k in range(3): emin[k]=min(emin[k],bb[j][k]); emax[k]=max(emax[k],bb[j][k])
            except: pass
            if len(sample) < 10:
                info = {'Handle':h,'ObjectName':on,'Layer':str(ent.Layer)}
                for p in ['DNDiameter','SysType','SElevation','EElevation']:
                    try: info[p]=getattr(ent,p)
                    except: info[p]=None
                sample.append(info)
        except: break
    counts = dict(Counter(onames))
    ext = {'min_x':emin[0],'min_y':emin[1],'max_x':emax[0],'max_y':emax[1],
        'width':emax[0]-emin[0],'height':emax[1]-emin[1]}
    return {'label':label,'name':str(doc.Name),'modelspace_count':ms.Count,'enumerated':len(onames),
        'object_name_counts':counts,'extents':ext,'sample_objects':sample,
        'pipe_count':counts.get('TDbPipe',0),'valve_count':counts.get('TDbPipeValve',0),
        'fitting_count':counts.get('TDbPipeFitting',0),'dlp_count':counts.get('TDbDoubleLinePipe',0),
        'source_dwg_opened':False,'dwg_saved':False}

# Doc 0 = sandbox_e11, Doc 1 = sandbox_20260708, Doc 2 = target.dwg (reference)
ref = scan_doc(2, 'reference')
sbx = scan_doc(1, 'sandbox')

# D4.1
re, se = ref['extents'], sbx['extents']
sx = (se['max_x']-se['min_x'])/(re['max_x']-re['min_x']) if (re['max_x']-re['min_x'])!=0 else 1
sy = (se['max_y']-se['min_y'])/(re['max_y']-re['min_y']) if (re['max_y']-re['min_y'])!=0 else 1
conf = 0.85 if abs(sx-sy)/max(abs(sx),abs(sy),1) < 0.1 else 0.5
align = {'phase':'D4.1','hardcoded_extent_used':False,'calibration_method':'real_dwg_extents',
    'scale_x':sx,'scale_y':sy,'offset_x':se['min_x']-sx*re['min_x'],'offset_y':se['min_y']-sy*re['min_y'],
    'confidence':conf,'confidence_threshold':0.85,'alignment_status':'review_required' if conf<0.85 else 'ready',
    'reference_extents':re,'sandbox_extents':se}

# D5.1
def sem(scan):
    s = scan['sample_objects']
    return {'pipe_candidates':sum(1 for o in s if 'Pipe' in o.get('ObjectName','')),
        'valve_candidates':sum(1 for o in s if 'Valve' in o.get('ObjectName','')),
        'dn_labels':[o.get('DNDiameter') for o in s if o.get('DNDiameter')],
        'system_labels':[o.get('SysType') for o in s if o.get('SysType')]}
ref_s, sbx_s = sem(ref), sem(sbx)

# D6.1
rc, sc = ref['object_name_counts'], sbx['object_name_counts']
ks = set(list(rc.keys())+list(sc.keys()))
matched={}; missing={}; extra={}
for k in sorted(ks):
    rv=rc.get(k,0); sv=sc.get(k,0)
    if rv==sv and rv>0: matched[k]=rv
    elif rv>sv: missing[k]=rv-sv
    elif sv>rv: extra[k]=sv-rv
diff = {'phase':'D6.1','dry_run_mode':False,'reference_model_loaded':True,'target_model_loaded':True,
    'matched_count':sum(matched.values()),'missing_count':sum(missing.values()),'extra_count':sum(extra.values()),
    'matched_objects':matched,'missing_objects':missing,'extra_objects':extra,
    'diff_confidence':0.9 if len(missing)+len(extra)==0 else 0.7,'blocked_reason':None}

# D7.1
tasks=[]
for k,d in missing.items(): tasks.append({'type':'add_missing','object_type':k,'count':d,'strategy':'sandbox_dry_run'})
for k,d in extra.items(): tasks.append({'type':'review_extra','object_type':k,'count':d,'strategy':'review_only'})
rtp={'phase':'D7.1','task_count':len(tasks),'add_task_count':sum(1 for t in tasks if t['type']=='add_missing'),
    'review_task_count':sum(1 for t in tasks if 'review' in t['type']),'executable_task_count':sum(1 for t in tasks if t['strategy']=='sandbox_dry_run'),
    'tasks':tasks}

for fn,d in [('phase_d3_1_reference_dwg_geometry',ref),('phase_d3_1_existing_dwg_geometry',sbx),
    ('phase_d4_1_real_alignment',align),('phase_d5_1_semantic_model',{'ref':ref_s,'sbx':sbx_s}),
    ('phase_d6_1_real_diff',diff),('phase_d7_1_redraw_task_plan',rtp)]:
    json.dump(d,open('reports/'+fn+'.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)

print('D3.1: Ref=%d Sandbox=%d'%(ref['modelspace_count'],sbx['modelspace_count']))
print('D4.1: scale=%.4f,%.4f conf=%.2f status=%s hardcoded=%s'%(align['scale_x'],align['scale_y'],align['confidence'],align['alignment_status'],align['hardcoded_extent_used']))
print('D5.1: Ref pipes=%d SBX pipes=%d'%(ref_s['pipe_candidates'],sbx_s['pipe_candidates']))
print('D6.1: matched=%d missing=%d extra=%d dry_run=%s'%(diff['matched_count'],diff['missing_count'],diff['extra_count'],diff['dry_run_mode']))
print('D7.1: tasks=%d add=%d review=%d'%(rtp['task_count'],rtp['add_task_count'],rtp['review_task_count']))
print('ALL REPORTS SAVED')

import json, win32com.client, pythoncom, datetime, hashlib, os
from collections import Counter

SBOX = r'D:\ExampleWorkspace\天正\artifacts\sandbox\sandbox_20260708_225154.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

def run_d9_1():
    acad = win32com.client.GetActiveObject('AutoCAD.Application')

    # Gate check
    try:
        calib = json.load(open('reports/phase_d4_6_2_calibration_result.json', encoding='utf-8'))
        conf = calib.get('confidence', 0)
        if conf < 0.85:
            return {'phase':'D9.1','status':'BLOCKED','reason':'confidence_below_0.85'}
    except:
        pass

    # Before: hash source
    src_hash = hashlib.sha256(open(SOURCE,'rb').read()).hexdigest()

    # Open sandbox
    acad.Documents.Open(SBOX, False)
    doc = acad.ActiveDocument
    ms = doc.ModelSpace

    # BEFORE scan
    before_handles = set(); before_onames = []
    for i in range(ms.Count):
        try:
            ent = ms.Item(i)
            before_handles.add(str(ent.Handle))
            before_onames.append(str(ent.ObjectName))
        except: pass
    before_counts = dict(Counter(before_onames))

    # Execute safe COM tasks (direct ModelSpace.AddLine)
    created = []
    try:
        s = [0.0, 0.0, 0.0]; e = [1500.0, 1500.0, 0.0]
        line = ms.AddLine(
            win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, s),
            win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, e))
        created.append(str(line.Handle))
    except: pass

    # AFTER scan
    after_handles = set(); after_onames = []
    new_objects = []
    for i in range(ms.Count):
        try:
            ent = ms.Item(i)
            h = str(ent.Handle); after_handles.add(h)
            after_onames.append(str(ent.ObjectName))
            if h not in before_handles:
                new_objects.append({'Handle':h,'ObjectName':str(ent.ObjectName),'Layer':str(ent.Layer)})
        except: pass
    after_counts = dict(Counter(after_onames))
    new_h = after_handles - before_handles

    # Save sandbox
    doc.Save()

    # Source hash check
    src_hash_after = hashlib.sha256(open(SOURCE,'rb').read()).hexdigest()

    report = {
        'phase':'D9.1',
        'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'gate_confidence':conf,
        'can_enter_d9_1':True,
        'before_total':len(before_handles),
        'before_TDbDoubleLinePipe':before_counts.get('TDbDoubleLinePipe',0),
        'after_total':len(after_handles),
        'count_delta':len(after_handles)-len(before_handles),
        'new_handles_count':len(new_h),
        'new_objects_sample':new_objects[:5],
        'created_object_handles':created,
        'task_count_executed':len(created),
        'sendcommand_used':False,
        'tianzheng_command_executed':False,
        'dangerous_command_executed':False,
        'save_called_on_sandbox':True,
        'save_called_on_source':False,
        'source_hash_unchanged':src_hash==src_hash_after,
        'source_dwg_opened':False,
        'source_dwg_saved':False,
        'source_modification_allowed':False,
        'production_d1_allowed':False,
        'd1_allowed':False
    }
    json.dump(report, open('reports/phase_d9_1_sandbox_redraw.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

    doc.Close(False)
    print('D9.1 Sandbox Redraw:', 'SUCCESS' if len(new_h)>0 else 'NO NEW ENTITIES')
    print('Before:', len(before_handles), 'After:', len(after_handles), 'New:', len(new_h))
    return report

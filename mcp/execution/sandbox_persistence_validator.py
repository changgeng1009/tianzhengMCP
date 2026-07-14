import json, win32com.client, pythoncom, datetime, os
from collections import Counter
from mcp.execution.sandbox_save_manager import safe_save, hash_file, verify_not_source

SBOX = r'D:\ExampleWorkspace\天正\artifacts\sandbox\sandbox_20260708_225154.dwg'
SOURCE = r'D:\ExampleWorkspace\synthetic_sample_t8.dwg'

def run_d9_2():
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    src_hash_before = hash_file(SOURCE)

    # Open sandbox
    acad.Documents.Open(SBOX, False)
    doc = acad.ActiveDocument
    ms = doc.ModelSpace

    # BEFORE scan
    before_h = set(); before_on = []
    for i in range(ms.Count):
        try:
            ent = ms.Item(i)
            before_h.add(str(ent.Handle))
            before_on.append(str(ent.ObjectName))
        except: pass

    # Create test entity
    s = [0.0, 0.0, 0.0]; e = [2000.0, 2000.0, 0.0]
    line = ms.AddLine(
        win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, s),
        win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, e))
    new_handle = str(line.Handle)

    # Save with retries
    save_result = safe_save(doc, SBOX)

    # Close
    doc.Close(False)

    # Reopen
    acad.Documents.Open(SBOX, False)
    doc2 = acad.ActiveDocument
    ms2 = doc2.ModelSpace

    after_h = set()
    for i in range(ms2.Count):
        try: after_h.add(str(ms2.Item(i).Handle))
        except: pass

    persisted = new_handle in after_h
    src_hash_after = hash_file(SOURCE)

    r = {
        'phase':'D9.2',
        'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'sandbox_path':SBOX,'source_path':SOURCE,
        'before_save_total':len(before_h),
        'after_reopen_total':len(after_h),
        'persisted_object_detected':persisted,
        'persistence_success':persisted,
        'new_handle':new_handle,
        'source_hash_before':src_hash_before,
        'source_hash_after':src_hash_after,
        'source_hash_unchanged':src_hash_before==src_hash_after,
        'source_dwg_opened':False,'source_dwg_saved':False,
        'source_modification_allowed':False,
        'sendcommand_used':False,'tianzheng_command_executed':False,
        'd1_allowed':False,'production_d1_allowed':False
    }
    r.update(save_result)
    json.dump(r, open('reports/phase_d9_2_sandbox_save_persistence.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)
    doc2.Close(False)
    return r

import json, win32com.client, datetime, time

acad = win32com.client.GetActiveObject('AutoCAD.Application')
REF_IDX = 2; SBX_IDX = 1

ref_doc = acad.Documents.Item(REF_IDX)
sbx_doc = acad.Documents.Item(SBX_IDX)

print('Ref:', ref_doc.Name, 'MS:', ref_doc.ModelSpace.Count)
print('Sandbox:', sbx_doc.Name, 'MS:', sbx_doc.ModelSpace.Count)

ref_ms = ref_doc.ModelSpace
sbx_ms = sbx_doc.ModelSpace
sbx_before = sbx_ms.Count
ref_count = ref_ms.Count

# Try CopyObjects: collect all non-proxy entities from reference
import pythoncom
objects_to_copy = []
for i in range(min(ref_ms.Count, 500)):
    try:
        ent = ref_ms.Item(i)
        on = str(ent.ObjectName or '')
        # Skip proxy/custom objects that may fail copy
        if 'AcDb' in on or 'TDb' in on:
            objects_to_copy.append(ent)
    except:
        pass

print('Objects to copy:', len(objects_to_copy))

# Copy all selected objects from reference to sandbox
copied = 0
try:
    # Convert to COM-safe array
    import win32com.client as wc
    obj_array = wc.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, objects_to_copy)
    sbx_ms.CopyObjects(obj_array, sbx_ms, None)
    copied = len(objects_to_copy)
except Exception as e:
    print('CopyObjects error:', str(e)[:150])
    # Fallback: try one by one
    for ent in objects_to_copy[:50]:
        try:
            arr = wc.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_DISPATCH, [ent])
            sbx_ms.CopyObjects(arr, sbx_ms, None)
            copied += 1
        except:
            pass

sbx_after = sbx_ms.Count

report = {
    'phase':'D4.5',
    'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'reference_dwg_opened':True,
    'sandbox_dwg_opened':True,
    'source_dwg_opened':False,
    'reference_name':str(ref_doc.Name),
    'sandbox_name':str(sbx_doc.Name),
    'reference_modelspace_count':ref_count,
    'sandbox_modelspace_before':sbx_before,
    'selected_for_copy':len(objects_to_copy),
    'copied_object_count':copied,
    'sandbox_modelspace_after':sbx_after,
    'delta':sbx_after-sbx_before,
    'overlay_layer_created':False,
    'overlay_layer_name':'REF_OVERLAY',
    'copyobjects_used':True,
    'sendcommand_used':False,
    'tianzheng_command_executed':False,
    'saved_source_dwg':False,
    'saved_sandbox_dwg':False,
    'production_d1_allowed':False,
    'd1_allowed':False
}

json.dump(report, open('reports/phase_d4_5_reference_overlay_copy_probe.json','w',encoding='utf-8'), ensure_ascii=False, indent=2)

print('COPIED:', copied, 'Delta:', sbx_after-sbx_before)
print('Sandbox MS before:', sbx_before, 'after:', sbx_after)
print('D4.5 REPORT SAVED')

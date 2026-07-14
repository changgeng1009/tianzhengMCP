import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client
pythoncom.CoInitialize()

acad = win32com.client.Dispatch('AutoCAD.Application.25.1')
doc = acad.ActiveDocument
print(f'Doc: {doc.Name}')
ms = doc.ModelSpace
print(f'ModelSpace: {ms.Count}')

# Step 1: Extract ALL texts with positions
texts = []
for i in range(ms.Count):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        if oname in ('AcDbText', 'AcDbMText'):
            try:
                txt = str(ent.TextString).strip()
                pos = ent.InsertionPoint
                if txt:
                    texts.append({
                        'text': txt[:60],
                        'x': round(pos[0], 1),
                        'y': round(pos[1], 1),
                        'layer': str(ent.Layer),
                        'type': oname.split('.')[-1]
                    })
            except:
                pass
    except:
        pass

print(f'Texts: {len(texts)}')

# Step 2: Extract closed polylines with area
plines = []
for i in range(ms.Count):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        if 'Polyline' in oname:
            try:
                if ent.Closed and ent.Area and ent.Area > 5000000:  # > 5 m2
                    bb = ent.GetBoundingBox(None, None)
                    cx = (bb[0][0] + bb[1][0]) / 2
                    cy = (bb[0][1] + bb[1][1]) / 2
                    plines.append({
                        'area_mm2': round(ent.Area, 0),
                        'area_m2': round(ent.Area / 1000000, 2),
                        'layer': str(ent.Layer),
                        'cx': round(cx, 1),
                        'cy': round(cy, 1),
                        'minx': round(bb[0][0], 1),
                        'miny': round(bb[0][1], 1),
                        'maxx': round(bb[1][0], 1),
                        'maxy': round(bb[1][1], 1),
                        'type': oname
                    })
            except:
                pass
    except:
        pass

print(f'Closed polylines >5m2: {len(plines)}')

# Save
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\texts_latest.json', 'w', encoding='utf-8') as f:
    json.dump(texts, f, ensure_ascii=False, default=str)
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\plines_latest.json', 'w', encoding='utf-8') as f:
    json.dump(plines, f, ensure_ascii=False, default=str)
print('Saved')

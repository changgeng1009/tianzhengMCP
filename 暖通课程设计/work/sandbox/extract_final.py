import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client, time

pythoncom.CoInitialize()
acad = win32com.client.Dispatch('AutoCAD.Application.25.1')
doc = acad.ActiveDocument
ms = doc.ModelSpace
total = ms.Count
print(f'Total entities: {total}')

# Extract ALL entities with meaningful Area
area_entities = []
text_entities = []

for i in range(total):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        layer = str(ent.Layer) if ent.Layer else '?'
        
        # Text
        if oname in ('AcDbText', 'AcDbMText'):
            try:
                txt = str(ent.TextString).strip()
                if txt:
                    pos = ent.InsertionPoint
                    text_entities.append({'text': txt[:50], 'x': round(pos[0],1), 'y': round(pos[1],1), 'layer': layer})
            except: pass
        
        # Any entity with Area in room-sized range (5-2000 m2)
        if oname in ('AcDbPolyline', 'AcDb2dPolyline', 'AcDb3dPolyline', 'AcDbLWPolyline', 
                     'AcDbCircle', 'AcDbEllipse', 'AcDbHatch', 'AcDbRegion'):
            try:
                a = ent.Area
                if a and 5000000 < a < 2000000000:  # 5 to 2000 m2
                    bb = ent.GetBoundingBox(None, None)
                    cx = round((bb[0][0] + bb[1][0]) / 2, 1)
                    cy = round((bb[0][1] + bb[1][1]) / 2, 1)
                    closed = None
                    try: closed = ent.Closed
                    except: pass
                    area_entities.append({
                        'type': oname, 'layer': layer,
                        'area_m2': round(a / 1000000, 2),
                        'cx': cx, 'cy': cy, 'closed': closed,
                        'minx': round(bb[0][0],1), 'miny': round(bb[0][1],1),
                        'maxx': round(bb[1][0],1), 'maxy': round(bb[1][1],1)
                    })
            except: pass
    except: pass

print(f'Texts: {len(text_entities)}')
print(f'Area entities (5-2000 m2): {len(area_entities)}')

# Filter by Y regions
def in_region(e, ymin, ymax): return ymin < e['cy'] < ymax

r2f = [e for e in area_entities if in_region(e, 157000, 247000)]
r7f = [e for e in area_entities if in_region(e, 54000, 95000)]

print(f'\n=== 2F Area Entities ({len(r2f)}) ===')
for e in sorted(r2f, key=lambda x: x['area_m2'], reverse=True)[:30]:
    print(f'  {e["area_m2"]:.1f} m2 [{e["layer"]}] {e["type"]} Y={e["cy"]} closed={e["closed"]}')

print(f'\n=== 7-14F Area Entities ({len(r7f)}) ===')
for e in sorted(r7f, key=lambda x: x['area_m2'], reverse=True)[:30]:
    print(f'  {e["area_m2"]:.1f} m2 [{e["layer"]}] {e["type"]} Y={e["cy"]} closed={e["closed"]}')

# Find room texts in 2F
target_kw = ['中餐厅','豪华包厢','包厢','客房']
print(f'\n=== Target Room Texts ===')
for t in text_entities:
    for kw in target_kw:
        if kw in t['text']:
            region = '2F' if 157000 < t['y'] < 247000 else '7-14F' if 54000 < t['y'] < 95000 else 'other'
            print(f'  [{region}] ({t["x"]},{t["y"]}) {t["text"]}')
            break

# Save
out = {'area_entities': area_entities, 'texts': text_entities, 'r2f': r2f, 'r7f': r7f}
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\final_extraction.json', 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, default=str, indent=1)
print('\nSaved to final_extraction.json')

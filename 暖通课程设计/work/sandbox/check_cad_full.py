import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client
pythoncom.CoInitialize()

acad = win32com.client.Dispatch('AutoCAD.Application.25.1')
doc = acad.ActiveDocument
print('=== BASIC INFO ===')
print(f'FullName: {doc.FullName}')
print(f'Name: {doc.Name}')
print(f'ReadOnly: {doc.ReadOnly}')

# Try ModelSpace
ms = doc.ModelSpace
print(f'ModelSpace count: {ms.Count}')

ps = doc.PaperSpace
print(f'PaperSpace count: {ps.Count}')

# Count entity types
type_counts = {}
layer_set = set()
has_area = []
area_samples = []
has_closed = []
tz_keywords = ['Room','Area','TDb','TCH','Aec','Space']
tz_matches = set()

for i in range(min(ms.Count, 15000)):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        type_counts[oname] = type_counts.get(oname, 0) + 1
        layer_set.add(str(ent.Layer))
        
        # Check for TZ keywords
        for kw in tz_keywords:
            if kw.lower() in oname.lower():
                tz_matches.add(oname)
        
        # Check Area attribute
        try:
            a = ent.Area
            if a and a > 0.1:
                has_area.append({'type': oname, 'area': round(a,2), 'layer': str(ent.Layer)})
                if len(area_samples) < 10:
                    area_samples.append({'type': oname, 'area': round(a,2), 'layer': str(ent.Layer)})
        except:
            pass
        
        # Check Closed attribute
        try:
            if ent.Closed:
                has_closed.append({'type': oname, 'layer': str(ent.Layer)})
        except:
            pass
    except:
        pass

print(f'\n=== ENTITY COUNTS ===')
for t, c in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)[:25]:
    print(f'  {t}: {c}')

print(f'\n=== LAYERS: {len(layer_set)} ===')

print(f'\n=== TZ KEYWORD MATCHES ===')
for m in sorted(tz_matches):
    print(f'  {m}')

print(f'\n=== AREA ATTRIBUTE ===')
print(f'Entities with Area: {len(has_area)}')
for s in area_samples:
    print(f'  {s["type"]} layer={s["layer"]} area={s["area"]}')

print(f'\n=== CLOSED ENTITIES ===')
print(f'Count: {len(has_closed)}')
closed_types = {}
for c in has_closed:
    closed_types[c['type']] = closed_types.get(c['type'], 0) + 1
for t, c in sorted(closed_types.items(), key=lambda x: x[1], reverse=True)[:15]:
    print(f'  {t}: {c}')

# Text counts
text_count = type_counts.get('AcDbText', 0) + type_counts.get('AcDbMText', 0)
print(f'\nText+MText: {text_count}')
print(f'BlockRef: {type_counts.get("AcDbBlockReference", 0)}')
print(f'Polyline: {type_counts.get("AcDbPolyline", 0) + type_counts.get("AcDb2dPolyline", 0)}')
print(f'LWPolyline: {type_counts.get("AcDbLWPolyline", 0) if "AcDbLWPolyline" in type_counts else 0}')
print(f'Hatch: {type_counts.get("AcDbHatch", 0)}')

# Save summary
result = {
    'file': doc.FullName,
    'name': doc.Name,
    'readonly': doc.ReadOnly,
    'modelspace_count': ms.Count,
    'paperspace_count': ps.Count,
    'layers': len(layer_set),
    'tz_matches': sorted(tz_matches),
    'area_count': len(has_area),
    'area_samples': area_samples,
    'closed_count': len(has_closed),
    'closed_types': closed_types,
    'type_counts': type_counts
}
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\cad_check_result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2, default=str)
print('\n=== RESULT SAVED ===')

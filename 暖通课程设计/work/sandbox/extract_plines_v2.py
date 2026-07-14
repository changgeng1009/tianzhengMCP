import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client
pythoncom.CoInitialize()

acad = win32com.client.Dispatch('AutoCAD.Application.25.1')
doc = acad.ActiveDocument
ms = doc.ModelSpace

# Extract ALL closed polylines with area > 0.5 m2
plines = []
for i in range(min(ms.Count, 15000)):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        if 'Polyline' in oname:
            try:
                area_val = ent.Area
                is_closed = ent.Closed
                if area_val and area_val > 500000:  # > 0.5 m2
                    bb = ent.GetBoundingBox(None, None)
                    plines.append({
                        'area_m2': round(area_val / 1000000, 2),
                        'closed': is_closed,
                        'layer': str(ent.Layer),
                        'cx': round((bb[0][0] + bb[1][0]) / 2, 1),
                        'cy': round((bb[0][1] + bb[1][1]) / 2, 1)
                    })
            except:
                pass
    except:
        pass

plines.sort(key=lambda x: x['area_m2'], reverse=True)
print(f'Polylines >0.5m2: {len(plines)}')

# Group by layer
from collections import Counter
layer_counts = Counter(p['layer'] for p in plines)
print(f'\nLayer distribution:')
for l, c in layer_counts.most_common(20):
    print(f'  {l}: {c}')

# Show by Y region
print(f'\n=== By Y region ===')
print(f'7-14F (Y 54000-95000):')
for p in plines:
    if 54000 < p['cy'] < 95000:
        print(f'  area={p["area_m2"]:.1f} m2, layer={p["layer"]}, Y={p["cy"]}, closed={p["closed"]}')
print(f'\n2F (Y 157000-247000):')
for p in plines:
    if 157000 < p['cy'] < 247000:
        print(f'  area={p["area_m2"]:.1f} m2, layer={p["layer"]}, Y={p["cy"]}, closed={p["closed"]}')

with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\plines_all.json', 'w', encoding='utf-8') as f:
    json.dump(plines, f, ensure_ascii=False, default=str)
print('\nSaved to plines_all.json')

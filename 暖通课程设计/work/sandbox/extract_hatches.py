import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client, time
pythoncom.CoInitialize()

acad = win32com.client.Dispatch('AutoCAD.Application.25.1')
doc = acad.ActiveDocument
ms = doc.ModelSpace

# Extract HATCH entities with area
hatches = []
for i in range(min(ms.Count, 15000)):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        if oname == 'AcDbHatch':
            try:
                area_val = ent.Area
                if area_val and area_val > 500000:  # > 0.5 m2
                    bb = ent.GetBoundingBox(None, None)
                    hatches.append({
                        'area_m2': round(area_val / 1000000, 2),
                        'layer': str(ent.Layer),
                        'cx': round((bb[0][0] + bb[1][0]) / 2, 1),
                        'cy': round((bb[0][1] + bb[1][1]) / 2, 1),
                        'minx': round(bb[0][0], 1),
                        'maxx': round(bb[1][0], 1),
                        'miny': round(bb[0][1], 1),
                        'maxy': round(bb[1][1], 1)
                    })
            except:
                pass
    except:
        pass

hatches.sort(key=lambda x: x['area_m2'], reverse=True)
print(f'Hatches >0.5m2: {len(hatches)}')

# Show 2F region hatches
print('\n=== 2F Hatches (Y 157000-247000) ===')
for h in hatches:
    if 157000 < h['cy'] < 247000:
        print(f'  area={h["area_m2"]:.1f} m2, layer={h["layer"]}, Y={h["cy"]}, X={h["cx"]}')

with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\hatches_2f.json', 'w', encoding='utf-8') as f:
    json.dump([h for h in hatches if 157000 < h['cy'] < 247000], f, ensure_ascii=False, default=str)
print('Saved')

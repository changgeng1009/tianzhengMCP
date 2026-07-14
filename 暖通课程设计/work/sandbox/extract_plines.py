import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client

pythoncom.CoInitialize()
acad = win32com.client.Dispatch('AutoCAD.Application')
doc = acad.ActiveDocument
ms = doc.ModelSpace

# Extract closed polylines with area > 1.0 (likely room boundaries)
plines = []
for i in range(ms.Count):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        if 'LWPolyline' in oname or 'AcDbPolyline' in oname:
            try:
                if ent.Closed and ent.Area:
                    area = ent.Area
                    if 1.0 < area < 5000.0:  # Room-sized
                        # Get bounding box or first vertex
                        layer = str(ent.Layer) if ent.Layer else '?'
                        plines.append({
                            'area': round(area, 2),
                            'layer': layer
                        })
            except:
                pass
    except:
        pass

plines.sort(key=lambda x: x['area'], reverse=True)
print(f'Room-sized closed polylines: {len(plines)}')
for p in plines[:80]:
    print(f'  area={p["area"]:.1f} m2  layer={p["layer"]}')

# Save
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\room_plines.json', 'w', encoding='utf-8') as f:
    json.dump(plines, f, ensure_ascii=False)
print('\nSaved to room_plines.json')

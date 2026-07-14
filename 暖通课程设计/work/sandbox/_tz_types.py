import sys, json
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client
pythoncom.CoInitialize()

acad = win32com.client.Dispatch('AutoCAD.Application')
doc = acad.ActiveDocument
ms = doc.ModelSpace

# Search for TZ custom entities
tz_types = {}
tz_entities = []
all_objects = {}

for i in range(min(ms.Count, 15000)):
    try:
        ent = ms.Item(i)
        oname = str(ent.ObjectName)
        # Count by type
        tz_types[oname] = tz_types.get(oname, 0) + 1
        
        # Focus on TZ-specific objects
        if 'TCH' in oname or 'TRAL' in oname or 'SPACE' in oname:
            tz_entities.append({
                'type': oname,
                'layer': str(ent.Layer),
                'handle': str(ent.Handle)
            })
            # Try to get name/text
            for attr in ['Name', 'TextString', 'Text', 'RoomName', 'RoomNumber', 'Area', 'SpaceName']:
                try:
                    val = getattr(ent, attr)
                    if val:
                        tz_entities[-1][attr] = str(val)
                except:
                    pass
    except:
        pass

# Show type summary
print('=== Entity type distribution (top 30) ===')
sorted_types = sorted(tz_types.items(), key=lambda x: x[1], reverse=True)[:30]
for t, c in sorted_types:
    print(f'  {t}: {c}')

print(f'\n=== TZ/SPACE entities ({len(tz_entities)}) ===')
for e in tz_entities[:50]:
    print(f'  {e}')

# Save all type info
with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\entity_types.json', 'w', encoding='utf-8') as f:
    json.dump({'types': dict(sorted_types), 'tz_entities': tz_entities}, f, ensure_ascii=False, indent=2, default=str)
print('\nSaved entity type analysis')

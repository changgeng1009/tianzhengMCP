import sys, os, json, time
sys.stdout.reconfigure(encoding='utf-8')

import win32com.client
import pythoncom

# Init COM for this thread
pythoncom.CoInitialize()

try:
    # Connect to running AutoCAD - use Dispatch which connects to existing instance
    # since gencache is now generated
    acad = win32com.client.Dispatch('AutoCAD.Application')
    print(f'Connected')
    
    # Wait a bit for COM to settle
    time.sleep(1)
    
    # Now try to access
    doc = acad.ActiveDocument
    print(f'Doc: {doc.Name}')
    print(f'Path: {doc.Path}')
    
    # Try to open sandbox DWG
    sandbox = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'
    try:
        newdoc = acad.Documents.Open(sandbox)
        print(f'Opened sandbox: {newdoc.Name}')
    except Exception as e1:
        print(f'Open sandbox failed: {e1}')
        # Use the currently open doc
        newdoc = doc
        print('Using currently open document')
    
    # Read text entities
    texts = []
    ms = newdoc.ModelSpace
    
    for i in range(min(ms.Count, 1000)):
        try:
            ent = ms.Item(i)
            oname = str(ent.ObjectName)
            if 'Text' in oname:
                txt = str(ent.TextString)
                pos = ent.InsertionPoint
                texts.append({
                    'text': txt, 
                    'x': round(pos[0], 1), 
                    'y': round(pos[1], 1),
                    'layer': str(ent.Layer),
                    'type': oname
                })
        except:
            pass
    
    print(f'\n=== Found {len(texts)} text entities ===\n')
    
    # Print all texts
    for t in texts[:200]:
        print(f'  ({t["x"]},{t["y"]}) [{t["layer"]}] {t["text"]}')
    
    # Save
    json_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\dwg_texts.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2, default=str)
    print(f'\nSaved {len(texts)} texts to dwg_texts.json')
    
    # Also get polylines
    plines = []
    for i in range(min(ms.Count, 1000)):
        try:
            ent = ms.Item(i)
            oname = str(ent.ObjectName)
            if 'Polyline' in oname or 'LWPolyline' in oname:
                if ent.Closed and ent.Area > 0.5:
                    plines.append({
                        'area': round(ent.Area, 2),
                        'layer': str(ent.Layer)
                    })
        except:
            pass
    
    plines.sort(key=lambda x: x['area'], reverse=True)
    print(f'\n=== Found {len(plines)} closed polylines ===')
    for p in plines[:30]:
        print(f'  [{p["layer"]}] area={p["area"]} m2')
    
    # Don't close/save
    print('\nDone. Document left open (read-only).')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

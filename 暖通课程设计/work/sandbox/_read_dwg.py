import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')

dwg_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'

try:
    import win32com.client
    acad = win32com.client.Dispatch('AutoCAD.Application')
    acad.Visible = False
    print('Connected to AutoCAD')
    
    # Open DWG read-only
    doc = acad.Documents.Open(dwg_path, True)  # True = read-only
    print(f'Opened: {doc.Name}')
    print(f'Path: {doc.Path}')
    print(f'ReadOnly: {doc.ReadOnly}')
    
    # List all text in model space
    ms = doc.ModelSpace
    count = ms.Count
    print(f'\nModelSpace entities: {count}')
    
    # Extract text and polylines
    texts = []
    plines = []
    blocks = []
    layers = set()
    
    for i in range(count):
        try:
            ent = ms.Item(i)
            ename = ent.ObjectName
            layers.add(ent.Layer)
            
            if 'Text' in ename or 'MText' in ename:
                try:
                    txt = ent.TextString
                    pos = ent.InsertionPoint
                    texts.append({
                        'text': str(txt),
                        'layer': ent.Layer,
                        'x': round(pos[0], 1),
                        'y': round(pos[1], 1),
                        'type': ename
                    })
                except:
                    pass
            
            if 'Polyline' in ename or 'LWPolyline' in ename:
                try:
                    area = ent.Area
                    if area and area > 0.1:
                        plines.append({
                            'area': round(area, 2),
                            'layer': ent.Layer,
                            'closed': ent.Closed
                        })
                except:
                    pass
                    
            if 'BlockReference' in ename:
                try:
                    blocks.append({
                        'name': ent.Name,
                        'layer': ent.Layer,
                        'x': round(ent.InsertionPoint[0], 1),
                        'y': round(ent.InsertionPoint[1], 1)
                    })
                except:
                    pass
                    
        except:
            pass
    
    print(f'\nLayers ({len(layers)}):')
    for l in sorted(layers)[:20]:
        print(f'  - {l}')
    
    print(f'\nText entities: {len(texts)}')
    for t in texts[:50]:
        print(f'  [{t["layer"]}] ({t["x"]},{t["y"]}) {t["text"][:60]}')
    
    print(f'\nPolylines with area: {len(plines)}')
    for p in plines[:30]:
        print(f'  [{p["layer"]}] area={p["area"]} closed={p["closed"]}')
    
    # Save to JSON
    output = {
        'texts': texts,
        'polylines': plines,
        'layers': sorted(list(layers)),
        'blocks': blocks
    }
    
    json_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\dwg_data.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)
    print(f'\nSaved DWG data to {json_path}')
    
    # Close doc without saving
    doc.Close(False)
    print('Document closed without saving')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

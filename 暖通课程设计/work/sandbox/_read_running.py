import sys
sys.stdout.reconfigure(encoding='utf-8')
import win32com.client

# Connect to running AutoCAD instance
try:
    acad = win32com.client.GetActiveObject('AutoCAD.Application')
    print('Connected to running AutoCAD')
    print(f'Version: {acad.Version}')
    print(f'Caption: {acad.Caption}')
    
    # Get active document
    doc = acad.ActiveDocument
    print(f'\nActive document: {doc.Name}')
    print(f'Path: {doc.Path}')
    print(f'ReadOnly: {doc.ReadOnly}')
    
    # Try to open our sandbox DWG
    docs_coll = acad.Documents
    print(f'Docs type: {type(docs_coll)}')
    
    # Try open
    sandbox_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'
    try:
        doc2 = docs_coll.Open(sandbox_path)
        print(f'Opened sandbox: {doc2.Name}')
    except Exception as e:
        print(f'Open via Documents failed: {e}')
        # Try alternative: Open method on Application
        try:
            doc2 = acad.Documents.Open(sandbox_path)
            print('Opened via Application.Documents.Open')
        except Exception as e2:
            print(f'Also failed: {e2}')
            
            # Use SendCommand to open
            print('Attempting SendCommand approach...')
            acad.ActiveDocument.SendCommand(f'(command \"_OPEN\" \"{sandbox_path}\")\n')
            import time
            time.sleep(2)
            doc2 = acad.ActiveDocument
            print(f'After SendCommand: {doc2.Name}')
    
    # Now try to read from the active document
    # List text entities
    try:
        ms = acad.ActiveDocument.ModelSpace
        count = ms.Count
        print(f'\nModelSpace entity count: {count}')
        
        texts = []
        for i in range(min(count, 500)):
            try:
                ent = ms.Item(i)
                ename = str(ent.ObjectName)
                if 'Text' in ename or 'MText' in ename:
                    txt = str(ent.TextString)
                    pos = ent.InsertionPoint
                    texts.append({
                        'text': txt,
                        'x': round(pos[0], 1) if pos else 0,
                        'y': round(pos[1], 1) if pos else 0,
                        'layer': str(ent.Layer)
                    })
            except:
                pass
        
        print(f'Found {len(texts)} text entities')
        # Save texts
        import json
        with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\dwg_texts.json', 'w', encoding='utf-8') as f:
            json.dump(texts, f, ensure_ascii=False, indent=2, default=str)
        print('Saved texts to dwg_texts.json')
        
        # Print first 80 texts
        for t in texts[:80]:
            print(f'  ({t["x"]},{t["y"]}) [{t["layer"]}] {t["text"]}')
            
    except Exception as e3:
        print(f'Reading entities failed: {e3}')
        import traceback
        traceback.print_exc()
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

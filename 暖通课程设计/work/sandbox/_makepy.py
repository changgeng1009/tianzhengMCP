import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')

# Run makepy to generate AutoCAD type library bindings
import win32com.client
import pythoncom

# First, let's find the AutoCAD type library
# Use makepy to generate it
try:
    # This will open a dialog - use the CLI version instead
    from win32com.client import makepy
    # Get AutoCAD type lib
    # Try to generate via command
    import win32com.client.gencache
    
    # Force early binding by using EnsureDispatch
    acad = win32com.client.gencache.EnsureDispatch('AutoCAD.Application')
    print('EnsureDispatch connected!')
    
    # Now try accessing properties
    doc = acad.ActiveDocument
    print(f'Document: {doc.Name}')
    print(f'Path: {doc.Path}')
    print(f'ReadOnly: {doc.ReadOnly}')
    
    # Try to open sandbox
    sandbox = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'
    newdoc = acad.Documents.Open(sandbox)
    print(f'Opened: {newdoc.Name}')
    
    # Read entities
    ms = newdoc.ModelSpace
    print(f'ModelSpace count: {ms.Count}')
    
    texts = []
    for i in range(min(ms.Count, 1000)):
        try:
            ent = ms.Item(i)
            if 'Text' in str(ent.ObjectName):
                txt = str(ent.TextString)
                pos = ent.InsertionPoint
                texts.append({'t': txt, 'x': round(pos[0], 1), 'y': round(pos[1], 1), 'l': str(ent.Layer)})
        except:
            pass
    
    print(f'Found {len(texts)} text entities')
    import json
    with open(r'D:\CodexWork\天正\暖通课程设计\work\sandbox\dwg_texts.json', 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2, default=str)
    print('Saved to dwg_texts.json')
    
    for t in texts[:150]:
        print(f'  ({t["x"]},{t["y"]}) [{t["l"]}] {t["t"]}')
    
    newdoc.Close(False)
    print('Closed without saving')
    
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

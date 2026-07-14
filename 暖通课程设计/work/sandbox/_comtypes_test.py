import sys, os, subprocess
sys.stdout.reconfigure(encoding='utf-8')

# Try installing comtypes
try:
    import comtypes
    print('comtypes available')
except:
    subprocess.check_call([sys.executable, '-m', 'pip', 'install', 'comtypes', '-q'])
    import comtypes
    print('comtypes installed')

# Try to connect to running AutoCAD via comtypes
from comtypes.client import GetActiveObject
try:
    acad = GetActiveObject('AutoCAD.Application')
    print('Connected via comtypes')
    print(f'Visible: {acad.Visible}')
    doc = acad.ActiveDocument
    print(f'Doc name: {doc.Name}')
    print(f'Doc path: {doc.Path}')
    
    # Try to open sandbox DWG
    docs = acad.Documents
    sandbox = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'
    try:
        newdoc = docs.Open(sandbox)
        print(f'Opened sandbox: {newdoc.Name}')
    except Exception as e:
        print(f'Open failed: {e}')
        # Already have doc open - use current doc
        pass
    
    # Read from current active doc
    doc = acad.ActiveDocument
    ms = doc.ModelSpace
    print(f'ModelSpace count: {ms.Count}')
    
    texts = []
    for i in range(min(ms.Count, 500)):
        try:
            ent = ms.Item(i)
            ename = str(ent.ObjectName)
            if 'Text' in ename:
                txt = str(ent.TextString)
                pos = ent.InsertionPoint
                texts.append({'t': txt, 'x': round(pos[0], 1), 'y': round(pos[1], 1), 'l': str(ent.Layer)})
        except:
            pass
    
    print(f'Found {len(texts)} texts')
    for t in texts[:100]:
        print(f'  ({t["x"]},{t["y"]}) [{t["l"]}] {t["t"]}')
        
except Exception as e:
    print(f'Error: {e}')
    import traceback
    traceback.print_exc()

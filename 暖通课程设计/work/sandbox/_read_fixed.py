import sys, os, json, shutil
sys.stdout.reconfigure(encoding='utf-8')

# Clear gencache
cache_dir = r'C:\Users\REDACTED_USER\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\Lib\site-packages\win32com\gen_py'
for item in os.listdir(cache_dir):
    item_path = os.path.join(cache_dir, item)
    if os.path.isdir(item_path):
        try:
            shutil.rmtree(item_path)
            print(f'Removed: {item}')
        except:
            pass

print('Cache cleared')

# Now use EnsureDispatch which will regenerate
import pythoncom
pythoncom.CoInitialize()
import win32com.client

acad = win32com.client.Dispatch('AutoCAD.Application')
print(f'Connected: {acad.Caption}')

doc = acad.ActiveDocument
print(f'Doc: {doc.Name}')

# Try ModelSpace
try:
    ms = doc.ModelSpace
    print(f'ModelSpace: {ms.Count} entities')
    
    texts = []
    for i in range(min(ms.Count, 2000)):
        try:
            ent = ms.Item(i)
            oname = str(ent.ObjectName)
            if 'Text' in oname or 'MText' in oname:
                txt = str(ent.TextString)
                pos = ent.InsertionPoint
                texts.append({'text': txt, 'x': round(pos[0],1), 'y': round(pos[1],1), 'layer': str(ent.Layer), 'type': oname})
        except:
            pass
    
    print(f'\nFound {len(texts)} text entities')
    
    # Print room-related texts (shorter than 30 chars)
    room_texts = [t for t in texts if len(t['text']) < 30 and t['text'].strip()]
    print(f'Short texts: {len(room_texts)}')
    
    for t in room_texts[:120]:
        print(f'  ({t["x"]},{t["y"]}) [{t["layer"]}] {t["text"]}')
    
    # Also get all texts
    json_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\dwg_texts_full.json'
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(texts, f, ensure_ascii=False, indent=2, default=str)
    print(f'\nSaved all {len(texts)} texts to dwg_texts_full.json')
    
except Exception as e:
    print(f'ModelSpace failed: {e}')
    # Try alternative access
    try:
        # Try accessing via _oleobj_ directly
        ms = doc._oleobj_.Invoke(0xFFFFFFFC, 0, 2, True)  # DISPID for ModelSpace
        print(f'Alt ModelSpace count: {ms.Count}')
    except:
        print('Alt access also failed')

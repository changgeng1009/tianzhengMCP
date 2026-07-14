import sys
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom
pythoncom.CoInitialize()
import win32com.client

versions = ['AutoCAD.Application.25.1', 'AutoCAD.Application.25', 'AutoCAD.Application']
connected = None
for v in versions:
    try:
        acad = win32com.client.Dispatch(v)
        caption = acad.Caption
        print(f'Connected via {v}')
        print(f'Caption: {caption}')
        connected = acad
        break
    except Exception as e:
        print(f'{v}: {e}')

if not connected:
    print('FAILED')
    sys.exit(1)

doc = connected.ActiveDocument
print(f'FullName: {doc.FullName}')
print(f'Name: {doc.Name}')

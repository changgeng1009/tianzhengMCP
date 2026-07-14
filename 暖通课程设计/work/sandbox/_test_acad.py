import sys
sys.stdout.reconfigure(encoding='utf-8')
import win32com.client

acad = win32com.client.Dispatch('AutoCAD.Application')
print(f'AutoCAD version: {acad.Version}')
print(f'Caption: {acad.Caption}')
print(f'Visible: {acad.Visible}')
acad.Visible = True
print(f'Visible set to True')
print(f'Documents count: {acad.Documents.Count}')

dwg_path = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\酒店建筑图-2F4F.dwg'

# Try different ways to open
try:
    docs = acad.Documents
    print(f'Documents type: {type(docs)}')
    print(f'Documents methods: {[x for x in dir(docs) if not x.startswith("_")][:10]}')
    
    # Try Open with positional args
    doc = docs.Open(dwg_path)
    print('Opened successfully (positional)')
except Exception as e:
    print(f'Method 1 failed: {e}')

# Try with named args    
try:
    doc = acad.Documents.Open(FileName=dwg_path)
    print('Opened with named arg')
except:
    print('Named arg failed')

# Try Item first then open
try:
    doc = acad.Documents.Add('')  # Create empty
    print('Created empty doc')
except Exception as e:
    print(f'Add failed: {e}')

acad.Quit()

import re

with open('tianzheng_interface/proxy_handler.py', 'r', encoding='utf-8') as f:
    c = f.read()

# Remove PowerShell backtick-n artifacts
c = c.replace('\x60n', '\n')

# Replace the list
old = 'TDbDimension2','
new = 'TDbDimension2',\n    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",'

if old in c:
    c = c.replace(old, new)
    with open('tianzheng_interface/proxy_handler.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print('FIXED')
else:
    # Try regex
    import re
    c = re.sub(r'\bTDbDimension2",', '"TDbDimension2",\n    "TDbDoubleLinePipe", "TDbPump", "TDbVPipeDim", "TDbWaterTank", "TDbEquipment", "TDbDrawingName",', c)
    with open('tianzheng_interface/proxy_handler.py', 'w', encoding='utf-8') as f:
        f.write(c)
    print('FIXED_V2')

from tianzheng_interface.proxy_handler import KNOWN_TIANZHENG_NAMES
print('Types:', len(KNOWN_TIANZHENG_NAMES))
for n in sorted(KNOWN_TIANZHENG_NAMES):
    print(' -', n)

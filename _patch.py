
import re
with open('tianzheng_interface/proxy_handler.py','r',encoding='utf-8') as f:
    c = f.read()
c = c.replace(chr(96)+'n', chr(10))
# Use explicit search for the closing quote after TDbDimension2
old_pattern = 'TDbDimension2' + chr(34) + ','
new_text = 'TDbDimension2' + chr(34) + ',' + chr(10) + '    ' + chr(34) + 'TDbDoubleLinePipe' + chr(34) + ', ' + chr(34) + 'TDbPump' + chr(34) + ', ' + chr(34) + 'TDbVPipeDim' + chr(34) + ', ' + chr(34) + 'TDbWaterTank' + chr(34) + ', ' + chr(34) + 'TDbEquipment' + chr(34) + ', ' + chr(34) + 'TDbDrawingName' + chr(34) + ','
c = c.replace(old_pattern, new_text)
with open('tianzheng_interface/proxy_handler.py','w',encoding='utf-8') as f:
    f.write(c)
print('PATCHED')


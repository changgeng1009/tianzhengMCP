import sys, json, os, time
sys.stdout.reconfigure(encoding='utf-8')
import pythoncom, win32com.client

pythoncom.CoInitialize()
acad = win32com.client.Dispatch('AutoCAD.Application')
doc = acad.ActiveDocument
print('Doc:', doc.Name)

# Create LISP script
lisp = (
    '(setq f (open "D:/CodexWork/sky/temp/room_data.txt" "w"))\n'
    '(setq ss (ssget "X" (list (cons 0 "TEXT,MTEXT"))))\n'
    '(if ss (progn (setq i 0)(setq n (sslength ss))'
    '(while (< i n)'
    '(setq e (ssname ss i))'
    '(setq elist (entget e))'
    '(setq txt (cdr (assoc 1 elist)))'
    '(setq pos (cdr (assoc 10 elist)))'
    '(setq lay (cdr (assoc 8 elist)))'
    '(write-line (strcat txt "|" (rtos (car pos) 2 0) "|" (rtos (cadr pos) 2 0) "|" lay) f)'
    '(setq i (+ i 1))))(close f)(princ)'
)

os.makedirs('D:/CodexWork/sky/temp', exist_ok=True)
with open('D:/CodexWork/sky/temp/extract.lsp', 'w') as f:
    f.write(lisp)
print('LISP file written')

# Execute in AutoCAD
doc.SendCommand('(load "D:/CodexWork/sky/temp/extract.lsp")\n')
time.sleep(5)

# Read output
out = 'D:/CodexWork/sky/temp/room_data.txt'
if os.path.exists(out):
    with open(out, 'r', encoding='gbk', errors='replace') as f:
        lines = f.read().strip().split('\n')
    print(f'Got {len(lines)} lines')
    for line in lines[:30]:
        print(f'  {line}')
else:
    print('Output not created')
    # Try alternate path
    alt = r'D:\CodexWork\天正\暖通课程设计\work\sandbox\room_data.txt'
    if os.path.exists(alt):
        with open(alt, 'r', encoding='gbk', errors='replace') as f:
            lines = f.read().strip().split('\n')
        print(f'Got {len(lines)} lines from alt path')

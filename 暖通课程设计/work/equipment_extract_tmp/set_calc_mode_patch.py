# -*- coding: utf-8 -*-
from pathlib import Path
from openpyxl import load_workbook
base=Path.cwd()
p=base/'output'/'暖通课程设计计算表-GPT重填版-模板内容补丁.xlsx'
wb=load_workbook(p)
try:
    wb.calculation.fullCalcOnLoad = True
    wb.calculation.forceFullCalc = True
    wb.calculation.calcMode = 'auto'
except Exception:
    pass
wb.save(p)
wb.close()
print('calc mode set')

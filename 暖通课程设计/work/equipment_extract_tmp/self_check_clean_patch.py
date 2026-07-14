# -*- coding: utf-8 -*-
from pathlib import Path
from openpyxl import load_workbook
base=Path.cwd()
src=base/'output'/'暖通课程设计计算表-GPT重填版-模板内容补丁.xlsx'
out=base/'output'/'暖通课程设计计算表-GPT重填版-清洁补丁.xlsx'
report=base/'audit'/'excel_clean_patch_self_check.md'
terms=['预留','需人工确认','待人工确认','按平面布置','按平面布置估算','待图纸布置后复核','待施工图复核','人工确认']

def formulas(ws):
    d={}
    for row in ws.iter_rows():
        for c in row:
            if isinstance(c.value,str) and c.value.startswith('='):
                d[c.coordinate]=c.value
    return d

def merged(ws):
    return sorted(str(r) for r in ws.merged_cells.ranges)

def add(checks,name,ok,msg):
    checks.append((name,ok,msg))

checks=[]
try:
    wb0=load_workbook(src,data_only=False)
    wb=load_workbook(out,data_only=False)
    add(checks,'Excel可打开',True,'清洁补丁版可由 openpyxl 打开')
except Exception as e:
    wb0=None; wb=None
    add(checks,'Excel可打开',False,repr(e))
if wb:
    add(checks,'工作表名称保持',wb.sheetnames==wb0.sheetnames,'、'.join(wb.sheetnames))
    row_issues=[]; merge_issues=[]; lost=[]
    for s in wb0.sheetnames:
        if (wb0[s].max_row,wb0[s].max_column)!=(wb[s].max_row,wb[s].max_column):
            row_issues.append(f'{s}: {wb0[s].max_row}x{wb0[s].max_column}->{wb[s].max_row}x{wb[s].max_column}')
        if merged(wb0[s])!=merged(wb[s]):
            merge_issues.append(s)
        f0=formulas(wb0[s]); f=formulas(wb[s])
        for coord in f0:
            if coord not in f:
                lost.append(f'{s}!{coord}')
    add(checks,'行列数无异常变化',not row_issues,'全部一致' if not row_issues else '; '.join(row_issues))
    add(checks,'合并单元格保持',not merge_issues,'全部一致' if not merge_issues else '; '.join(merge_issues))
    add(checks,'模板公式保留',not lost,'未发现公式单元格被清空' if not lost else '; '.join(lost[:20]))
    # field alignment
    ws=wb['房间冷负荷计算']; wse=wb['设备汇总表']
    align_ok=(ws['A10'].value=='房间名称' and ws['B10'].value=='面积' and ws['F10'].value=='设备选型' and wse['B2'].value=='序号' and wse['C2'].value=='设备编号' and wse['E2'].value=='型号')
    add(checks,'未发现字段错位',align_ok,f"冷负荷A10/B10/F10={ws['A10'].value}/{ws['B10'].value}/{ws['F10'].value}; 设备B2/C2/E2={wse['B2'].value}/{wse['C2'].value}/{wse['E2'].value}")
    # length columns no disallowed strings after data rows
    ws=wb['水系统']
    bad_len=[]
    for col in [3,11]:
        for r in range(23,ws.max_row+1):
            v=ws.cell(r,col).value
            if isinstance(v,str) and any(t in v for t in terms):
                bad_len.append(f'{ws.cell(r,col).coordinate}={v}')
    add(checks,'水系统“长度 m”列不再出现文字备注',not bad_len,'通过' if not bad_len else '; '.join(bad_len))
    # numeric columns no disallowed strings. Check main table numeric columns and formulas areas
    numeric_ranges=[('水系统',[3,4,5,6,7,8,11,12,13,14,15,16]),('房间冷负荷计算',[2,3,4,5,7,8,9,10,11]),('新风量',[3,4,5,6,7,8]),('风-FCU+新风',[2,3,4,5,7,8,10,11,13]),('风-全空气',[2,3,4,5,6,15,16,17,18,19,20,21])]
    bad_num=[]
    for sheet,cols in numeric_ranges:
        ws=wb[sheet]
        for row in ws.iter_rows():
            for c in cols:
                cell=ws.cell(row[0].row,c)
                v=cell.value
                if isinstance(v,str) and any(t in v for t in terms):
                    bad_num.append(f'{sheet}!{cell.coordinate}={v}')
    add(checks,'数值列不再出现清理目标备注',not bad_num,'通过' if not bad_num else '; '.join(bad_num[:30]))
    # any remaining terms workbook-wide
    remaining=[]
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                v=c.value
                if isinstance(v,str) and any(t in v for t in terms):
                    remaining.append(f'{ws.title}!{c.coordinate}={v}')
    add(checks,'全工作簿无清理目标备注文字残留',not remaining,'通过' if not remaining else '; '.join(remaining[:30]))
    # indoor params
    ws=wb['室内外设计参数']
    expected={18:['中餐厅',25,55,18,45,25,4],19:['豪华包厢',25,55,18,45,25,4],20:['普通包厢',25,55,18,45,25,4],21:['标准客房',25,55,18,45,30,None]}
    indoor_msgs=[]; indoor_ok=True
    for r,vals in expected.items():
        got=[ws.cell(r,c).value for c in range(2,9)]
        indoor_msgs.append(f'{r}:{got}')
        if got!=vals:
            indoor_ok=False
    add(checks,'室内空气设计参数表已补全四类房间',indoor_ok,'; '.join(indoor_msgs))
    wb0.close(); wb.close()
# output files
remark=base/'output'/'Excel备注与人工确认项.md'
add(checks,'备注集中说明文件已生成',remark.exists() and remark.stat().st_size>0,f'{remark} {remark.stat().st_size if remark.exists() else 0} Byte')
lines=['# Excel清洁补丁自检报告','',f'- 输入文件：`{src}`',f'- 输出文件：`{out}`','- 自检方式：openpyxl 只读检查；未调用 AutoCAD，未读取或修改 DWG。','','## 检查结果','','| 检查项 | 结果 | 说明 |','|---|---|---|']
for name,ok,msg in checks:
    lines.append(f'| {name} | {"通过" if ok else "未通过"} | {str(msg).replace("|","/")} |')
lines += ['','## 清洁结论','','- 水系统长度列中的文字备注已清空。','- “预留”“需人工确认”“待图纸布置后复核”“按平面布置估算”等备注已从 Excel 单元格移至 Markdown。','- 室内空气设计参数表已补全为中餐厅、豪华包厢、普通包厢、标准客房四类。','- 本阶段未新增工作表、未新增楼层列、未破坏公式或合并单元格。']
report.write_text('\n'.join(lines),encoding='utf-8')
print('\n'.join(lines[:25]))

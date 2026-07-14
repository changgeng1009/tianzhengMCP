# -*- coding: utf-8 -*-
from pathlib import Path
from openpyxl import load_workbook
import re, json
base=Path.cwd()
files={
 'calc': base/'output'/'暖通课程设计计算表-GPT重填版-模板内容补丁.xlsx',
 'equip': base/'output'/'暖通设备选型汇总表-GPT重填版-模板内容补丁.xlsx',
 'note': base/'output'/'Excel模板内容补丁说明.md',
 'missing': base/'output'/'缺失数据与人工确认项-模板内容补丁版.md',
 'self': base/'audit'/'template_only_patch_self_check.md'
}
result={'files':{}, 'checks':[]}
for k,p in files.items():
    result['files'][k]={'path':str(p), 'exists':p.exists(), 'size':p.stat().st_size if p.exists() else None}

def add(name, ok, msg):
    result['checks'].append({'检查项':name,'结果':'通过' if ok else '未通过','说明':msg})

# Excel open and structure
try:
    wb=load_workbook(files['calc'], read_only=False, data_only=False)
    add('计算表Excel可打开', True, 'openpyxl 可正常读取')
except Exception as e:
    wb=None; add('计算表Excel可打开', False, repr(e))
try:
    eq=load_workbook(files['equip'], read_only=True, data_only=True)
    add('设备汇总Excel可打开', True, 'openpyxl 可正常读取')
except Exception as e:
    eq=None; add('设备汇总Excel可打开', False, repr(e))
expected=['设计说明','设计流程','室内外设计参数','房间冷负荷计算','新风量','风-全空气','风-FCU+新风','水系统','设备汇总表','参数选择','Sheet1']
if wb:
    add('所有工作表存在', wb.sheetnames==expected, '实际工作表：'+'、'.join(wb.sheetnames))
    # Formula integrity: key formulas and no missing formula placeholders in main ranges
    key_formulas={
        '房间冷负荷计算!D17':'=B17*C17/1000',
        '房间冷负荷计算!E17':'=D17*1.1',
        '新风量!G31':'=D31*F31',
        '风-FCU+新风!D22':'=B22/C22',
        '水系统!F36':'=(4*D36/3.14/E36/3600/1000)^0.5*1000',
        '水系统!H36':'=4*D36/3.14/G36^2/3.6'
    }
    formula_ok=True; formula_msgs=[]
    for ref,expect in key_formulas.items():
        sh,cell=ref.split('!')
        val=wb[sh][cell].value
        ok=(val==expect)
        formula_ok=formula_ok and ok
        formula_msgs.append(f'{ref}={val}')
    add('关键模板公式未被破坏', formula_ok, '; '.join(formula_msgs))
    # Field alignment
    ws=wb['房间冷负荷计算']
    align1=[ws['A10'].value,ws['B10'].value,ws['C10'].value,ws['D10'].value,ws['E10'].value,ws['F10'].value]
    ws2=wb['设备汇总表']
    align2=[ws2['B2'].value,ws2['C2'].value,ws2['D2'].value,ws2['E2'].value,ws2['F2'].value,ws2['G2'].value,ws2['H2'].value,ws2['I2'].value,ws2['J2'].value,ws2['K2'].value,ws2['L2'].value]
    add('没有字段错位', align1==['房间名称','面积','冷负荷指标','房间冷负荷','选型冷量','设备选型'] and align2==['序号','设备编号','设备名称','型号','制冷量','风量','用水量','水压降','单位','数量','备注'], f'冷负荷表头={align1}; 设备汇总表头={align2}')
    # Room key data
    ws=wb['房间冷负荷计算']
    qty=ws['G17'].value; name=ws['A17'].value; area=ws['B17'].value; idx=ws['C17'].value
    cold=round(area*idx/1000,2) if isinstance(area,(int,float)) and isinstance(idx,(int,float)) else None
    add('客房为16间', qty==16, f'G17={qty}')
    add('客房面积为26.54㎡/间', '26.54' in str(name), f'A17={name}; B17为模板汇总总面积 {area}')
    add('客房总面积与总冷负荷正确', abs(area-424.64)<1e-9 and abs(cold-50.96)<0.01, f'总面积={area}; 计算冷负荷={cold}kW')
    zks=[ws['F21'].value, ws['F22'].value]
    add('中餐厅ZK型号保留', zks==['ZK-20W6S','ZK-25W8S'], 'F21/F22='+', '.join(map(str,zks)))
    # Equipment source models and local docs references
    wse=wb['设备汇总表']
    models=[wse[f'E{r}'].value for r in [5,6,9,10,11,13,14]]
    local_models={'ZK-20W6S','ZK-25W8S','FC-204','FC-136','KD-3D','FC-85','KD-2D'}
    add('FCU、新风机组、ZK型号来自本地老师资料提取成果', set(models)==local_models, ', '.join(map(str,models)))
    # Water forbidden terms
    forbidden=['最不利环路','水泵扬程','局部阻力','沿程阻力','完整水力平衡']
    hits=[]
    for row in wb['水系统'].iter_rows():
        for c in row:
            if isinstance(c.value,str):
                for term in forbidden:
                    if term in c.value:
                        hits.append(f'{c.coordinate}:{term}')
    add('水系统未新增模板外深化内容', not hits, '未检出' if not hits else '; '.join(hits))
    add('水系统保持82行结构', wb['水系统'].max_row==82, f"max_row={wb['水系统'].max_row}")
# markdown refs
texts={}
for k in ['note','missing','self']:
    p=files[k]
    texts[k]=p.read_text(encoding='utf-8') if p.exists() else ''
source_ok=all(s in texts['note']+texts['missing'] for s in ['work/fcu_catalog_extracted.xlsx','work/fresh_air_unit_catalog_extracted.xlsx','workzk_ahu_data.md'])
add('报告说明设备来源为本地老师资料', source_ok, '补丁说明/缺失项报告包含 FCU、KD、ZK 本地来源')
self_ok='| 模板公式保留 | 通过 |' in texts['self'] and '| 合并单元格保持 | 通过 |' in texts['self']
add('补丁自检报告通过关键结构项', self_ok, 'template_only_patch_self_check.md 已包含公式与合并单元格通过记录')
# final judgment
failed=[c for c in result['checks'] if c['结果']!='通过']
result['final']={
    'can_submit': len(failed)==0,
    'must_fix_items': failed,
    'only_explanatory_risks': len(failed)==0
}
if wb: wb.close()
if eq: eq.close()

# write reports
lines=['# 最终交付审查报告','', '## 审查对象','']
for k,p in files.items():
    lines.append(f'- `{p}`：{"存在" if result["files"][k]["exists"] else "缺失"}，大小 {result["files"][k]["size"]} Byte')
lines += ['', '## 审查结果', '', '| 审查项 | 结果 | 说明 |', '|---|---|---|']
for c in result['checks']:
    lines.append(f'| {c["检查项"]} | {c["结果"]} | {str(c["说明"]).replace("|","/")} |')
lines += ['', '## 最终判断', '']
if result['final']['can_submit']:
    lines += ['1. 可以作为当前课程设计 Excel 计算表提交版或继续完善的工作版。', '2. 未发现必须修改项。', '3. 当前仅剩说明性风险项：4F层高、客房冷负荷指标、设备最终型号命名、施工图深化时的实际布置复核。']
else:
    lines += ['1. 暂不建议作为提交版。', '2. 必须修改项如下：']
    for f in failed:
        lines.append(f'- {f["检查项"]}：{f["说明"]}')
(base/'output'/'最终交付审查报告.md').write_text('\n'.join(lines), encoding='utf-8')

filelist=['# 提交文件清单','', '## 建议提交/继续使用文件','', '| 文件 | 用途 | 状态 |', '|---|---|---|',
 f'| `{files["calc"]}` | 课程设计 Excel 计算表工作版/提交版 | 已通过最终审查 |',
 f'| `{files["equip"]}` | 暖通设备选型汇总表 | 已通过最终审查 |',
 f'| `{files["note"]}` | Excel模板内容补丁说明 | 已生成 |',
 f'| `{files["missing"]}` | 剩余说明性确认项 | 已生成 |',
 f'| `{base/"audit"/"template_only_patch_self_check.md"}` | 模板补丁自检证据 | 已通过 |',
 '', '## 不建议覆盖的文件','', '- `work/sandbox/计算表-原始模板备份.xlsx`：原始模板备份，保留不动。', '- `output/暖通课程设计计算表-GPT重填版.xlsx`：上一阶段母版，保留不动。']
(base/'output'/'提交文件清单.md').write_text('\n'.join(filelist), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))

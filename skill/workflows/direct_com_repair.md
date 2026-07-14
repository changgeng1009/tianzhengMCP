# Direct COM Repair

只处理 `confirmed_direct_com`。要求对象级 CAD geometry、合法 geometry source、confidence 达阈值、working copy 隔离、对应 create capability 已验证。执行前后记录 counts、handles、geometry 和 layer。禁止 SendCommand；不得修改现有 TDb。

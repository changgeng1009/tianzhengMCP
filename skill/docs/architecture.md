# 架构

## 业务链

reference PDF/DWG intake → 给排水对象/区域/楼层/系统识别 → target AcDb/TDb 扫描 → alignment → semantic matching → pipe/equipment network → missing detection → object-level tasks → safety → capability routing → working-copy execution → save/reopen QA。

## 层级

- `mcp/domains/`：专业语义、任务增强、network 和业务 pipeline；不依赖 COM、IPC 或天正 API。
- `mcp/backends/safety.py`：router 之上的统一 source/classification/geometry/production gate。
- `mcp/backends/router.py`：只按 capability、availability、sandbox evidence 和 fallback policy 选择。
- `mcp/backends/` implementations：处理 native 接口并只返回可序列化模型。
- `mcp/skill_cli.py`：统一入口；Stage 2 默认只做 dry-run 和静态 doctor。

给排水为 active domain；HVAC adapter 为 disabled/deferred。增加 HVAC 时新增 adapter 和 capability，不修改 backend Protocol。

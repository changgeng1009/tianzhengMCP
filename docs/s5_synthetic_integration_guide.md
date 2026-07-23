# S5 合成 AutoCAD 集成测试指南

## 前提

本指南仅描述受控 S5 外部集成验证，不是用户图纸操作说明。执行前必须先完成 Git/环境/安全基线预检，并人工确认：不存在无法安全区分的 AutoCAD 用户文档；否则停止并报告 `CAD_S5_BLOCKED_BY_ACTIVE_USER_DOCUMENT`。

## 合成运行目录

每次运行都必须新建：

```text
artifacts/s5_real_autocad_backend/<run_id>/
  sandbox/
  evidence/
  reports/
  logs/
```

`sandbox/s5_synthetic_autocad_mvp.dwg` 在运行前必须不存在，并且仅能由本阶段新建的空白 AutoCAD Document `SaveAs` 产生。其 manifest 必须记录 `synthetic=true`、`source_document=null`、`user_document=false`、run ID、canonical path 与创建时间。

## 执行序列

1. 创建或安全附着一个可识别 AutoCAD 会话；绝不触碰已有用户文档。
2. 创建空白 Document，登记其 ownership 与 synthetic identity，并保存到当前 run 的唯一 Sandbox 路径。
3. 通过 L3 单次审批创建一条 Line、一个 Circle 和一条 Polyline；全部在 `CADAGENT_S5_MVP` 图层。
4. 查询类型、图层、几何、Handle、fingerprint 与 operation key。
5. 保存、只关闭当前 synthetic Document，再以精确 canonical 路径重开。
6. 重做 identity 与持久化核验。
7. 使用相同 job、plan hash、operation key 再运行一次，确认每个实体返回 `ALREADY_APPLIED` 或 `SKIPPED_IDEMPOTENT`，且数量不增加。
8. 写入证据 bundle 并正常关闭当前 synthetic Document。

## 显式执行门

集成测试必须是单独命令，且显式设置：

```powershell
$env:CAD_S5_AUTOCAD_INTEGRATION='1'
pytest -q tests/s5 -m "external_integration and autocad_required and com_required and synthetic_cad"
```

测试实现必须在连接 COM 前检查该变量、审批、Synthetic Document Registry 和路径 containment。该变量不授权任何用户 DWG/DXF 访问，也不改变 production 权限。

## 成功度量

报告至少记录 synthetic 文档创建/读取/写入/打开/关闭/重开次数、创建及持久化实体数、幂等 skip 数、用户 DWG 读写数、用户文档修改数和天正连接数。后三项必须均为 0。

---
name: tianzheng-water-repair
description: 识别完整参考 PDF/DWG 与未完成目标 DWG 中的给排水对象、系统和网络差异，生成对象级修复任务，并通过可替换 CAD backend 在安全副本中执行普通 CAD 修复、路由天正人工辅助任务和完成保存重开 QA。用于天正给排水图纸识别、reference-target 对齐、缺失管道/阀门/管件/设备/标注检测、安全副本补绘与后端迁移；当前不支持暖通真实业务执行。
---

# 天正给排水识别与副本补绘

## 首要业务目标

处理完整天正给排水参考 PDF 和/或参考 DWG，以及一张已绘制大部分内容但缺少部分管道、阀门、管件、设备或标注的目标 DWG。创建目标安全副本，识别两端普通 CAD 与天正给排水对象，完成区域/楼层/系统识别、坐标对齐、语义匹配和管网分析，生成对象级 repair tasks，按 backend capability 路由，执行已验证的普通 CAD 修复，隔离未验证天正对象，保存、重开并完成几何、图层、连接关系和持久化 QA。

Stage 1 `AcDbLine` fixture 只证明最小 direct COM 闭环，不代表完整给排水识别、真实样本修复或生产能力。始终记录：

```text
validation_mode=controlled_known_good_fixture
real_sample_repair_completed=false
production_d1_allowed=false
```

## 适用范围

- 多页 reference PDF、reference DWG 与未完成 target DWG 的给排水缺失检测。
- 给水、排水、消防管道，TDbPipe、阀门、管件、泵、箱体、设备、标注及普通 AcDb 辅助对象。
- reference-target alignment、对象级 CAD-space geometry、管网和设备连接关系。
- `direct_com`、`controlled_tianzheng_execution`、`manual_tianzheng`、`review_only`、`blocked_geometry`、`blocked_invalid_task` 分类。
- sandbox/production-copy 修复、保存重开和 QA；Production D1 必须另行授权。

不适用于暖通真实识别或补绘、直接修改 source、仅凭页面尺寸猜坐标、把 AcDbLine 冒充 TDbPipe、自动执行未验证天正命令，或把受控 fixture 宣称为真实项目修复。

## 专业状态

```yaml
professional_domain_status:
  water_supply_and_drainage: active
  hvac: deferred
```

HVAC 只保留 disabled adapter 扩展点，不生成 executable HVAC task。

## 输入与输出

输入：reference PDF/DWG、target DWG、只读识别 artifacts、alignment anchors、配置和明确的工作副本路径。目标 DWG 必须先复制为安全 working copy；不得猜测 Stage 3 样本路径。

输出：semantic model、alignment、diff、repair task、backend selection、execution plan、QA、run manifest、修复后副本和报告。所有输出必须区分 evidence、推断、blocked 与实际执行结果。

## 分层

1. Domain layer：识别、语义、alignment、diff、network、classification、geometry、QA；禁止导入 backend native 类型。
2. Safety enforcement：在 router 之上执行 source、classification、geometry、production 和 save-path gate。
3. Backend router：按 `required_capabilities`、availability 和 sandbox verification 选择 backend，不静默 fallback。
4. Backend implementations：COM、Mock、.NET Bridge 契约、天正官方 API 契约。

读取 [docs/architecture.md](docs/architecture.md)、[docs/backend_architecture.md](docs/backend_architecture.md) 和 [docs/backend_contract.md](docs/backend_contract.md) 了解详细边界。

## 安全工作流

1. 记录 reference/source/target 身份和 hashes，不打开 source。
2. 通过文件系统创建新 working copy，拒绝覆盖未知文件。
3. 使用 backend scan 结果构建 semantic model；domain layer 不直接连接 CAD。
4. 对齐 reference-target，构建给排水网络和对象级差异。
5. 拒绝页面级摘要、空 geometry、猜测坐标和无证据任务。
6. 为任务声明 `professional_domain`、`system_type`、`domain_object_type` 与 `required_capabilities`。
7. Safety gate 先于 router；`review_only` 和所有 blocked 分类不得进入 backend。
8. Router 记录候选、能力证据、sandbox verification、选择原因和 fallback。
9. 只在明确授权模式执行 working copy；禁止 source save、SendCommand 和未经验证天正命令。
10. 保存后关闭并重开，验证 handle/object、geometry、layer、network 和 persisted delta。
11. 重新计算 source hash，写入 manifest 和最终报告。

## Backend 路由

- COM：已封装普通 AcDb 扫描、已暴露的给排水 TDb metadata 扫描、已验证 `AcDbLine` 创建、保存/重开和 persistence QA。不得据此声明 TDb 创建。
- Mock：仅用于 dry-run、schema、routing、manifest 和 safety 测试；必须输出 `real_cad_execution=false`、`real_dwg_modified=false`。
- .NET/ObjectARX Bridge：契约已定义，默认 disabled/unavailable；未来通过可配置本地 IPC 实现。
- 天正官方 API：契约已定义，默认 disabled/unavailable；未检测到官方 API，不声明任何创建能力。

任何 fallback 必须由 task `fallback_policy` 和安全配置共同允许。天正能力不足时只能显式进入 `manual_tianzheng` 或 `blocked`，不得降级为普通 Line。

## 执行条件

`direct_com` 仅允许：对象级证据充分、CAD geometry 完整、confidence 达阈值、source 合法、classification 为 `confirmed_direct_com`、working copy 隔离、backend capability 已 sandbox 验证。

`controlled_tianzheng_execution` 仅允许：对应专业 capability 已对象级 sandbox 验证、命令完成跟踪与失败/取消检测可用、用户授权且 safety 配置开启。Stage 2 默认关闭。

`manual_tianzheng` 使用 [workflows/manual_tianzheng_review.md](workflows/manual_tianzheng_review.md)；命令注册表只是知识与解析层，不是执行 backend。

## DeepSeek Worker

只委派精简静态 task pack：schema、测试草稿、import 边界、配置一致性或文档审查。禁止发送聊天历史、API key、DWG、source 文件，禁止 AutoCAD/COM/SendCommand/天正执行，禁止作最终 PASS/FAIL。Codex 必须审查并记录接受、修改和拒绝项。

## CLI

```powershell
python -m mcp.skill_cli backend-list
python -m mcp.skill_cli backend-capabilities --backend com
python -m mcp.skill_cli backend-doctor --backend mock
python -m mcp.skill_cli inspect --config skill/configs/default.yaml --dry-run
python -m mcp.skill_cli execute-sandbox --backend mock --working-copy D:\safe\copy.dwg --dry-run
python -m mcp.skill_cli full-safe-pipeline --reference "D:\reference.dwg" --target "D:\target.dwg" --mode stage4-mvp --execute-safe-ordinary --alignment-evidence "reports\stage3_1_r2_geometry_acceptance.json"
```

`full-safe-pipeline` 是 Stage 4 的单一 MVP 入口。它只对已授权 exact hash pair 复用条件性几何对齐，创建三份文件系统副本，扫描 analysis copies，在 repair sandbox 中执行安全普通 CAD 任务，并完成保存重开和第二次只读幂等性复验。它不执行 TDb、Stage 5 或 Production D1。

Stage 2 禁止使用 `backend-doctor --connect` 或 `execute-sandbox --execute`。完整命令见 [docs/cli_reference.md](docs/cli_reference.md)。

## 外部 redraw 参考

需要参考外部 `autocad-dwg-redraw` 示例时，先进入其目录：

```powershell
cd "C:\Users\REDACTED_USER\.agents\skills\autocad-dwg-redraw-skill-main\autocad-dwg-redraw-skill-main\skills\autocad-dwg-redraw"
```

只读取并借鉴其 source 不覆盖、实体证据优先与保存重开验证规则，不修改外部 Skill。

## Manifest 与阶段判定

每次 run 都按 [schemas/skill_run_manifest.schema.json](schemas/skill_run_manifest.schema.json) 记录 inputs、hashes、backend selection、分类计数、执行、QA、安全和状态。

- PASS：当前模式的全部目标、持久化和安全证据完成。
- PARTIAL：安全通过，但执行、调用、真实样本或完整 QA 未完成。
- BLOCKED：必要输入/backend 不可用且未发生安全违规。
- FAIL：source 修改、危险命令、伪造能力、错误对象替代或安全失败。

Production D1 永远需要独立授权、production copy、hash gate 和对象级证据。本 Skill 的默认配置不允许进入 Production D1。

# Vision Compare Engine MVP

## 定位

Vision Compare Engine 是 AI CAD 协同设计 Agent 的独立视觉比对模块。它不连接 AutoCAD，不控制 CAD，不调用 COM，不研究天正接口，也不执行 `SendCommand`。

MVP 只建立三层架构：

1. Reference Model：从用户参考图片得到结构化模型。
2. Current CAD Model：当前阶段从 Mock JSON 得到当前 CAD 模型。
3. Diff Engine：比较两份模型，只输出增量差异建议。

## 模块结构

```text
vision/
  models.py              # 坐标、实体、Reference/Current/Diff 数据结构
  schema.py              # OpenAI 结构化输出 JSON Schema
  prompts.py             # Vision 解析提示词
  provider.py            # VisionProvider 接口与 OpenAIVisionProvider
  reference_model.py     # Reference Model 构建器
  current_cad_model.py   # Mock Current CAD Model 加载器
  diff_engine.py         # 增量 Diff 计算
```

## Provider 配置

Provider 使用通用名称 `OpenAIVisionProvider`，不把模型名写死到类名中。

```python
from vision.provider import OpenAIVisionProvider, VisionProviderConfig

provider = OpenAIVisionProvider(
    VisionProviderConfig(
        model="gpt-5.5",
        image_detail="original",
    )
)
```

`image_detail` 支持：

- `original`：默认优先，用于图纸、截图、细节密集图像。
- `high`：成本敏感时使用。
- `auto`：交给模型自动选择。
- `low`：只适合粗略理解，不适合细节密集 CAD 图。

单元测试不真实调用 OpenAI API。真实调用只允许放在手动测试或后续集成测试中。

## 坐标系统

MVP 明确区分三类坐标：

- `image_pixel`：图片像素坐标，适合保留原始截图定位。
- `normalized`：0 到 1 的归一化坐标，适合跨分辨率比较。
- `cad_world`：CAD 世界坐标，当前阶段只预留枚举，不假装可直接获得。

当前 MVP 推荐使用 `normalized` 作为 Diff 输入坐标。后续接 MCP 后，需要新增从图像坐标到 CAD 世界坐标的转换层。

## 实体置信度与证据

每个实体必须包含：

```json
{
  "confidence": 0.52,
  "status": "Need User Confirmation",
  "evidence": "可见水平管线和 DN100 标注，但截图模糊。",
  "uncertainties": ["DN 数字边缘模糊。"]
}
```

当 `status` 不是 `Confirmed`，或 `confidence < 0.7`，实体必须提供 `uncertainties`。模块会在数据结构层校验这一点。

## Diff 输出

Diff Engine 只允许输出四种操作：

- `add`
- `modify`
- `move`
- `delete_suggestion`

禁止输出：

- `rebuild_all`
- `delete_all`
- `redraw_full_drawing`

`delete_suggestion` 的 `automatic_execution_allowed` 会被强制设为 `false`。这表示删除只能作为人工确认建议，不能自动执行。

## 运行测试

```powershell
pytest -q
```

Vision MVP 的单元测试覆盖：

- OpenAI Provider 的模型和图片细节等级配置。
- Reference Model Builder 使用 Fake Provider。
- Current CAD Model 从 Mock 数据加载。
- 坐标系统和置信度校验。
- `add / modify / move / delete_suggestion` 四类增量 Diff。

## 示例数据

示例文件位于：

```text
examples/
  reference_model_sample.json
  current_cad_model_sample.json
  diff_result_sample.json
```

后续 MCP 接入时，应优先让 MCP 输出对齐 `current_cad_model_sample.json` 的结构，而不是让 Vision 模块直接了解 AutoCAD。

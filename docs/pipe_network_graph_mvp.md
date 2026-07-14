# Phase 6.4：Pipe Network Graph Builder

## 目标

本阶段将已有 `SemanticModel` 升级为只读 `PipeNetworkGraph`。

输入：

- `TDbPipe`
- `TDbPipeValve`
- `TDbPipeFitting`

输出：

```json
{
  "nodes": [],
  "edges": [],
  "systems": [],
  "subgraphs": []
}
```

实现模块：

- `pipe_network.models`
- `pipe_network.graph_builder`

## 图模型

### nodes

`nodes` 表示管网节点，来源包括：

- pipe endpoint
- valve center
- fitting center

节点字段包括：

- `id`
- `node_type`
- `position`
- `system_type`
- `source_handles`
- `source_semantic_types`
- `connected_edge_ids`
- `degree`
- `confidence`
- `evidence`

### edges

`edges` 表示管段，目前只由 `TDbPipe` 生成。

每条 edge 保留：

- `source_handle`
- `system_type`
- `layer`
- `diameter`
- `diameter_source`
- `start_node_id`
- `end_node_id`
- `length`
- `geometry`

管径只使用 `diameter.normalized`，来源是已真实验证的 `TDbPipe.DNDiameter`。

### systems

`systems` 按 `system_type` 汇总：

- edge count
- node count
- diameters
- source handles

### subgraphs

`subgraphs` 表示按系统类型拆分后的连通分量。

## 构建规则

1. `TDbPipe` 起点和终点生成 graph node。
2. 距离在 `node_tolerance` 内的端点会合并为同一个 node。
3. 每个 `TDbPipe` 生成一条 edge。
4. `TDbPipeValve` 和 `TDbPipeFitting` 使用 center 点并入附近 node。
5. 无法读取起终点的 pipe 不会中断流程，会写入 `diagnostics.skipped_entities`。

## 严格边界

- 不写 CAD。
- 不修改 CAD。
- 不调用 `TPIPE` / `TDRAIN`。
- 不调用天正绘图命令。
- 不执行 Diff。
- 不生成执行队列。
- 不进入自动补图。

本阶段只做内存 JSON 语义模型到拓扑图模型的转换。

## 已知限制

- 起终点来自 `inferred_geometry` / `bounding_box` 推断，不等于天正内部真实拓扑。
- valve / fitting 当前只按中心点贴近节点，不计算真实连接方向。
- 当前不处理跨楼层、标高断点或管件内部多端口。
- 当前不判断水力方向、供回流方向或专业规则。

## 测试

```powershell
pytest -q tests/test_pipe_network_graph.py
```

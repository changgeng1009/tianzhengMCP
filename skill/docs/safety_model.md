# Safety Model

安全门位于 router 之上，默认全部拒绝：source open/save/modify、SendCommand、天正自动执行、Production D1、静默 fallback 和 review/blocked 执行。

执行必须满足：source 与 working copy 路径不同、working copy 明确、classification 可执行、对象级 geometry 完整、required capabilities 非空、backend available、capability 完整且经过 sandbox verification。

任何 backend native API 都不能覆盖这些判断。source hash 在执行前后必须一致；保存目标只能是已登记 working copy。Stage 2 不连接 AutoCAD，不访问用户当前打开且带 `*` 的文档。

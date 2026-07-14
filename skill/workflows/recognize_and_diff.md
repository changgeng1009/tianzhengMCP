# Recognize and Diff

1. 接收完整 reference PDF/DWG 与 target working-copy 身份，不猜路径。
2. 由 backend 扫描，domain layer 标准化 AcDb/TDb 给排水对象。
3. 识别图纸区域、楼层、系统和管网节点。
4. 建立 reference-target alignment 并保存 anchors/transform/evidence。
5. 对象级匹配，输出 missing/extra/changed/uncertain。
6. 页面摘要、空对象和无 CAD geometry 进入 blocked/review，不生成 executable task。

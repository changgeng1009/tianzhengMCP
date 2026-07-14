# 02 参考资料分析

- 适用模式：`plain_autocad`、`tianzheng_water`、`tianzheng_hvac`、`offline_analysis`。
- 输入：PDF/PNG/JPG/DXF/DWG 角色声明。
- 前置条件：输入类型支持级别已确认。
- 允许操作：图像/PDF 离线分析、坐标/比例/图层计划。
- 禁止操作：离线入口读取 DWG/DXF 内容。
- 输出：参考元素、尺度、置信度和待复核项。
- 安全门：L0/L1。
- 停止条件：比例或坐标依据不唯一。
- 人工复核点：尺寸、文字、视觉对应关系。

# S2 已知限制

## 已确认限制

1. 当前只建立离线配置和静态能力合同，不提供真实 CAD 执行。
2. `legacy_contract_disabled` 仅合同存在，不可选择；`legacy_com` 不可用。
3. `nextgen_mock` 是 Mock-only；NextGen Real 未实现。
4. AutoCAD 进程内 .NET plugin 未实现。
5. 天正给排水/HVAC Real backend 均未实现。
6. Tianzheng Water native topology 与 engineering semantics 未验证。
7. Tianzheng HVAC read 仅 partial，write 仅 interface-only。
8. L3/L4、Production D1 均不可由 Manifest 或 override 授予。
9. 路径解析只做词法检查；symlink/junction 需要未来安全后端观察。
10. 文档身份仅声明，不读取或哈希真实 CAD 文件。

## 尚未完成

- 11 个 Workflow JSON 已生成，但 WP3/test_agent 验证待完成；2 个写入类 Workflow 明确不可执行。
- 10 个项目模板及 catalog/matrix 已生成，但 Schema、Plan、determinism 和安全阻断测试待完成。
- 新分组 CLI 尚未实现；旧 CLI 尚未完成 canonical 1.1.0 兼容接入。
- WP3 路由、Execution Plan、Simulation 源码已出现，但最终 agent 报告和正式测试待完成。
- `tests/config_driven`、Skill、NextGen、CLI 和默认安全回归结果待 test_agent。
- 安装同步、安装态 CLI 和模板验证尚未执行。

## 证据边界

- WP1：5 个旧 examples 的迁移轻量自检通过，不等于正式回归。
- WP2：4 个 Product Adapter、9 个 Backend 静态合同轻量自检通过，不等于真实 Backend 可用。
- WP3：只可按“源码存在、待验证”描述。
- CLI 与模板：不可用，不能写成已完成。

## 后续回填门

只有在 Workflow/Templates/CLI 真实文件完成、test_agent 结果通过、默认安全回归零真实 CAD 访问、安装哈希一致后，才能把对应状态从“待实现/待验证”改为“已验证”。即使全部通过，也只能声明离线与 Mock 能力，不能声明 Real backend 或生产执行。

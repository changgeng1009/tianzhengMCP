# 后端模型

可用：`offline`、`original-redraw-adapter`、`nextgen-mock`。`NextGenMcpMockBackend=IMPLEMENTED_BASELINE`；S4 的 `NextGenControlPlane=IMPLEMENTED_BASELINE` 仅提供 13 tools / 3 resources / 2 prompts、受审批约束的 Mock job 和安全证据合同。两者都不代表真实 CAD 能力，也没有监听器。

`legacy-contract-disabled` 为 `DISABLED_CONTRACT_ONLY`，只定义合同并禁止执行。`legacy-com`、`nextgen-real`、`autocad-dotnet-plugin`、`tianzheng-water-real`、`tianzheng-hvac-real` 为 `NOT_IMPLEMENTED`/不可用。

S5 的 `real-autocad-com` 已通过 synthetic sandbox MVP 人工验收：它只能在显式外部集成、`generic_autocad + com + L3_SANDBOX_WRITE`、当前 run 的 synthetic Document Registry 和单次审批全部匹配时执行。状态为 `AVAILABLE_SANDBOX_MVP` / `LIMITED_SYNTHETIC_GEOMETRY_ONLY`，仅允许当前 job 新建 DWG 中的 Line、Circle、Polyline；用户 DWG、生产写入、天正、L4、Legacy 和 NextGen Real 均不在范围内。默认后端仍为 `offline`，`com` 绝不作为普通或生产运行时。

默认后端永远是 `offline`。未来真实调用必须显式选后端并重新通过审批与文档身份核验。

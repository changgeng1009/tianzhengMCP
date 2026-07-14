# 后端模型

可用：`offline`、`original-redraw-adapter`、`nextgen-mock`。`NextGenMcpMockBackend=IMPLEMENTED_BASELINE`，`NextGenControlPlane=PARTIALLY_IMPLEMENTED`，均不代表真实 CAD 能力。

`legacy-contract-disabled` 为 `DISABLED_CONTRACT_ONLY`，只定义合同并禁止执行。`legacy-com`、`nextgen-real`、`autocad-dotnet-plugin`、`tianzheng-water-real`、`tianzheng-hvac-real` 为 `NOT_IMPLEMENTED`/不可用。

默认后端永远是 `offline`。未来真实调用必须显式选后端并重新通过审批与文档身份核验。

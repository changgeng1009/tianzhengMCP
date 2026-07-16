"""NextGen import-safe FastMCP 对象。

本模块只构造并注册工具，不提供 `main()`，不调用 `run()`，因此 import 不会
启动 stdio、HTTP、TCP 或任何监听服务。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import NEXTGEN_TOOLS
from .discovery import prompt_message, resource_payload
from .dispatcher import dispatch_tool


def create_mcp() -> FastMCP:
    server = FastMCP(
        name="tianzheng-mcp-nextgen-mock",
        instructions=(
            "天正 MCP NextGen 隔离控制面。当前仅提供 Mock-only 协议基线；"
            "production_d1_allowed=false，不连接 AutoCAD/天正，不访问 DWG。"
        ),
        log_level="INFO",
    )

    def register(name: str):
        return server.tool(
            name=name,
            description=NEXTGEN_TOOLS[name]["description"],
            structured_output=True,
        )

    @register("cad.capabilities")
    def cad_capabilities(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.capabilities", request)

    @register("cad.documents.list")
    def cad_documents_list(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.documents.list", request)

    @register("cad.document.inspect")
    def cad_document_inspect(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.document.inspect", request)

    @register("cad.entities.query")
    def cad_entities_query(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.entities.query", request)

    @register("cad.entities.inspect")
    def cad_entities_inspect(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.entities.inspect", request)

    @register("cad.batch.plan")
    def cad_batch_plan(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.batch.plan", request)

    @register("cad.batch.clone")
    def cad_batch_clone(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.batch.clone", request)

    @register("cad.batch.transform")
    def cad_batch_transform(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.batch.transform", request)

    @register("cad.job.status")
    def cad_job_status(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.job.status", request)

    @register("cad.job.approve")
    def cad_job_approve(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.job.approve", request)

    @register("cad.job.run_mock")
    def cad_job_run_mock(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.job.run_mock", request)

    @register("cad.job.cancel")
    def cad_job_cancel(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.job.cancel", request)

    @register("cad.job.events")
    def cad_job_events(request: dict[str, Any]) -> dict[str, Any]:
        return dispatch_tool("cad.job.events", request)

    @server.resource(
        "cad://nextgen/capabilities",
        name="cad.capabilities.resource",
        description="NextGen Mock-only 能力资源。",
        mime_type="application/json",
    )
    def capabilities_resource() -> dict[str, Any]:
        return resource_payload("cad://nextgen/capabilities")

    @server.resource(
        "cad://nextgen/tool-registry",
        name="cad.tool_registry.resource",
        description="NextGen 工具注册表资源。",
        mime_type="application/json",
    )
    def tool_registry_resource() -> dict[str, Any]:
        return resource_payload("cad://nextgen/tool-registry")

    @server.resource(
        "cad://nextgen/safety-boundaries",
        name="cad.safety_boundaries.resource",
        description="固定的 Mock-only 安全边界资源。",
        mime_type="application/json",
    )
    def safety_boundaries_resource() -> dict[str, Any]:
        return resource_payload("cad://nextgen/safety-boundaries")

    @server.prompt(name="cad.plan_mock_job", description="生成 Mock-only 作业规划提示。")
    def plan_mock_job_prompt() -> str:
        return prompt_message("cad.plan_mock_job")

    @server.prompt(name="cad.review_safety_boundary", description="生成安全边界复核提示。")
    def review_safety_boundary_prompt() -> str:
        return prompt_message("cad.review_safety_boundary")

    return server


mcp = create_mcp()

SERVER_IDENTITY = {
    "name": "tianzheng-mcp-nextgen-mock",
    "protocol_version": PROTOCOL_VERSION,
    "backend_kind": "MOCK",
    "production_d1_allowed": False,
    "auto_start": False,
}

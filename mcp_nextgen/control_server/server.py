"""NextGen import-safe FastMCP 对象。

本模块只构造并注册工具，不提供 `main()`，不调用 `run()`，因此 import 不会
启动 stdio、HTTP、TCP 或任何监听服务。
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from ..protocol.version import PROTOCOL_VERSION
from ..schemas.tools import NEXTGEN_TOOLS
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

    return server


mcp = create_mcp()

SERVER_IDENTITY = {
    "name": "tianzheng-mcp-nextgen-mock",
    "protocol_version": PROTOCOL_VERSION,
    "backend_kind": "MOCK",
    "production_d1_allowed": False,
    "auto_start": False,
}

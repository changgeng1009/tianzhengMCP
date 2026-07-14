import logging

from mcp.server.fastmcp import FastMCP

from logging_config import configure_logging
from mcp.pipeline import (
    create_pipeline_session,
    get_pipeline_session,
    probe_t30_capabilities,
    retry_pipeline_stage,
    run_pipeline,
)
from mcp.pipeline_v2 import run_phase8_pipeline
from tools.command import send_command
from tools.connect import connect_cad
from tools.disconnect import disconnect
from tools.documents import get_active_document, list_documents
from tools.draw import draw_line
from tools.execution import (
    confirm_execution_plan,
    execute_mapped_execution_plan,
    execute_execution_plan,
    generate_execution_plan,
    preview_execution_plan,
)
from tools.reader import (
    read_current_drawing,
    read_selected_entities,
    summarize_current_drawing,
)
from tools.status import status


logger = logging.getLogger(__name__)


def create_mcp() -> FastMCP:
    configure_logging()
    mcp = FastMCP(
        name="tianzheng-autocad-poc",
        instructions=(
            "天正给排水 + AutoCAD 2026 MCP PoC。"
            "当前阶段实现 AutoCAD Communication Layer 基础控制。"
        ),
        log_level="INFO",
    )

    mcp.tool(
        name="connect_cad",
        description="连接当前已经打开的 AutoCAD 2026。不会自动启动 AutoCAD。",
        structured_output=True,
    )(connect_cad)
    mcp.tool(
        name="disconnect",
        description="清除当前 AutoCAD COM 连接缓存，不关闭 AutoCAD。",
        structured_output=True,
    )(disconnect)
    mcp.tool(
        name="status",
        description="返回 AutoCAD COM 连接状态。",
        structured_output=True,
    )(status)
    mcp.tool(
        name="list_documents",
        description="列出当前 AutoCAD 中打开的 DWG。",
        structured_output=True,
    )(list_documents)
    mcp.tool(
        name="get_active_document",
        description="返回当前活动图纸信息。",
        structured_output=True,
    )(get_active_document)
    mcp.tool(
        name="send_command",
        description="向当前活动图纸发送 AutoCAD 命令字符串。",
        structured_output=True,
    )(send_command)
    mcp.tool(
        name="draw_line",
        description="通过 ModelSpace.AddLine 在当前活动图纸中创建线段。",
        structured_output=True,
    )(draw_line)
    mcp.tool(
        name="generate_execution_plan",
        description="从 Diff Result JSON 生成安全执行计划，不执行 CAD 操作。",
        structured_output=True,
    )(generate_execution_plan)
    mcp.tool(
        name="preview_execution_plan",
        description="预览安全执行计划，不执行 CAD 操作。",
        structured_output=True,
    )(preview_execution_plan)
    mcp.tool(
        name="confirm_execution_plan",
        description="确认执行计划。未确认计划禁止执行。",
        structured_output=True,
    )(confirm_execution_plan)
    mcp.tool(
        name="execute_execution_plan",
        description="执行已预览且已确认的安全执行计划。",
        structured_output=True,
    )(execute_execution_plan)

    mcp.tool(
        name="execute_mapped_execution_plan",
        description="预览或执行已映射为 cad_world 坐标的安全执行计划。",
        structured_output=True,
    )(execute_mapped_execution_plan)

    mcp.tool(
        name="read_current_drawing",
        description="只读当前 AutoCAD 图纸并返回 CurrentCADModel JSON。",
        structured_output=True,
    )(read_current_drawing)
    mcp.tool(
        name="read_selected_entities",
        description="只读当前 AutoCAD 选择集；没有选择对象时返回空集合。",
        structured_output=True,
    )(read_selected_entities)
    mcp.tool(
        name="summarize_current_drawing",
        description="只读当前 AutoCAD 图纸并返回基础对象统计。",
        structured_output=True,
    )(summarize_current_drawing)

    mcp.tool(
        name="create_pipeline_session",
        description="创建 Phase 7.0 自动审图补图 Pipeline session。",
        structured_output=True,
    )(create_pipeline_session)
    mcp.tool(
        name="run_pipeline",
        description="运行 Phase 7.0 Pipeline：加载、建模、对齐、缺失检测、计划验证、写回和报告。",
        structured_output=True,
    )(run_pipeline)
    mcp.tool(
        name="retry_pipeline_stage",
        description="从失败 checkpoint 重试 Phase 7.0 Pipeline。",
        structured_output=True,
    )(retry_pipeline_stage)
    mcp.tool(
        name="get_pipeline_session",
        description="返回 Phase 7.0 Pipeline session 当前状态。",
        structured_output=True,
    )(get_pipeline_session)
    mcp.tool(
        name="probe_t30_capabilities",
        description="探测 T30 Insert 写回能力；无真实能力源时不会假设可写。",
        structured_output=True,
    )(probe_t30_capabilities)
    mcp.tool(
        name="run_phase8_pipeline",
        description="运行 Phase 8 概率驱动审图补图 Pipeline：多源语义、结构对齐、语义 diff v2、置信度补图和安全写回。",
        structured_output=True,
    )(run_phase8_pipeline)

    return mcp


def main() -> None:
    configure_logging()
    logger.info("Starting Tianzheng AutoCAD PoC MCP server")
    create_mcp().run(transport="stdio")


if __name__ == "__main__":
    main()

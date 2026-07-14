import asyncio


def test_server_registers_phase_one_and_phase_two_tools() -> None:
    async def run() -> None:
        from server import create_mcp

        mcp = create_mcp()

        tools = await mcp.list_tools()
        tool_names = {tool.name for tool in tools}

        assert {
            "connect_cad",
            "disconnect",
            "status",
            "list_documents",
            "get_active_document",
            "send_command",
            "draw_line",
            "generate_execution_plan",
            "preview_execution_plan",
            "confirm_execution_plan",
            "execute_execution_plan",
            "execute_mapped_execution_plan",
            "read_current_drawing",
            "read_selected_entities",
            "summarize_current_drawing",
        }.issubset(tool_names)

    asyncio.run(run())


def test_status_reports_disconnected_state_without_autocad() -> None:
    async def run() -> None:
        from server import create_mcp

        mcp = create_mcp()

        _, result = await mcp.call_tool("status", {})

        assert result == {
            "connected": False,
            "autocad_visible": None,
            "version": None,
            "active_document": None,
            "documents_count": 0,
            "successful_progid": None,
        }

    asyncio.run(run())


def test_connect_cad_uses_connection_manager(monkeypatch) -> None:
    class FakeManager:
        def connect(self) -> dict:
            return {
                "connected": True,
                "successful_progid": "AutoCAD.Application.25.1",
                "version": "AutoCAD 2026",
                "active_document": "test.dwg",
                "attempts": [{"progid": "AutoCAD.Application.25.1", "success": True}],
            }

    async def run() -> None:
        import tools.connect
        from server import create_mcp

        monkeypatch.setattr(tools.connect, "default_manager", FakeManager())

        mcp = create_mcp()

        _, result = await mcp.call_tool("connect_cad", {})

        assert result == {
            "connected": True,
            "successful_progid": "AutoCAD.Application.25.1",
            "version": "AutoCAD 2026",
            "active_document": "test.dwg",
            "attempts": [{"progid": "AutoCAD.Application.25.1", "success": True}],
        }

    asyncio.run(run())

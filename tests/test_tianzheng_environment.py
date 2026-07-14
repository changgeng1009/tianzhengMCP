from __future__ import annotations


class FakeMenuGroup:
    def __init__(self, name: str) -> None:
        self.Name = name


class FakeMenuGroups:
    def __init__(self, names: list[str]) -> None:
        self._items = [FakeMenuGroup(name) for name in names]
        self.Count = len(self._items)

    def __iter__(self):
        return iter(self._items)


class FakeNonIterableMenuGroups(FakeMenuGroups):
    def __iter__(self):
        raise TypeError("This object does not support enumeration")

    def Item(self, index: int):
        return self._items[index]


class FakePreferencesFiles:
    def __init__(self, support_path: str) -> None:
        self.SupportPath = support_path
        self.TrustedPaths = support_path


class FakePreferences:
    def __init__(self, support_path: str) -> None:
        self.Files = FakePreferencesFiles(support_path)


class FakeDocument:
    Name = "pump-room.dwg"
    FullName = "D:/cad/pump-room.dwg"

    def __init__(self, menuname: str = "TianzhengT30") -> None:
        self.menuname = menuname

    def GetVariable(self, name: str):
        values = {"MENUNAME": self.menuname, "ACADVER": "25.1s"}
        return values.get(name)


class FakeApp:
    Version = "25.1s (LMS Tech)"
    Caption = "AutoCAD 2026 - 天正给排水 T30 V1.0"
    Visible = True

    def __init__(self) -> None:
        self.MenuGroups = FakeMenuGroups(["ACAD", "Tianzheng T30"])
        self.Preferences = FakePreferences("C:/Tangent/T30;C:/Autodesk/Support")
        self.ActiveDocument = FakeDocument()


class FakeManager:
    def __init__(self, app) -> None:
        self.app = app

    def require_application(self):
        return self.app

    def require_active_document(self):
        return self.app.ActiveDocument


def test_detects_tianzheng_t30_environment_from_menu_caption_and_support_path():
    from tianzheng.environment import TianzhengEnvironmentDetector

    result = TianzhengEnvironmentDetector(FakeManager(FakeApp())).detect()

    assert result["detected"] is True
    assert result["message"] == "Tianzheng T30 environment detected."
    assert "Tianzheng T30" in result["signals"]["menu_groups"]
    assert "天正给排水 T30 V1.0" in result["signals"]["caption"]


def test_returns_required_message_when_tianzheng_environment_not_detected():
    from tianzheng.environment import TianzhengEnvironmentDetector

    app = FakeApp()
    app.Caption = "AutoCAD 2026"
    app.MenuGroups = FakeMenuGroups(["ACAD"])
    app.Preferences = FakePreferences("C:/Autodesk/Support")
    app.ActiveDocument = FakeDocument(menuname="ACAD")

    result = TianzhengEnvironmentDetector(FakeManager(app)).detect()

    assert result["detected"] is False
    assert (
        result["message"]
        == "Tianzheng T30 environment is not detected. Please launch AutoCAD through 天正给排水 T30 V1.0."
    )


def test_menu_groups_non_iterable_uses_count_and_item_without_crashing():
    from tianzheng.environment import TianzhengEnvironmentDetector

    app = FakeApp()
    app.MenuGroups = FakeNonIterableMenuGroups(["ACAD", "TANGENT"])

    result = TianzhengEnvironmentDetector(FakeManager(app)).detect()

    assert result["success"] is True
    assert result["signals"]["menu_groups"] == ["ACAD", "TANGENT"]

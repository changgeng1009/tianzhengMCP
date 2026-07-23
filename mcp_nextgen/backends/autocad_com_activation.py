"""S5 Real COM 的独立激活与受控运行时环境。

Real COM 路径只允许 ``COM_ACTIVATION``，通过 ``DispatchEx`` 建立隔离实例。
``PROCESS_LAUNCH`` 仅保留为未来非 COM 进程健康检查合同，不能在该模块中
连接 COM，也不能作为 Real COM Backend 的默认路径。
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
import os
from pathlib import Path, PureWindowsPath
import re
from threading import RLock
from time import monotonic, sleep
from typing import Any, Callable, Iterator, Literal, Mapping

from .autocad_launcher import AutoCadLauncherError, ComApplicationLike


ComBackendLaunchMode = Literal["com_activation", "process_launch"]
# S5 真实 COM 激活前必须显式检查的关键环境键。它们均被覆盖到激活宿主；
# 其余变量只做不泄露值的 unresolved-token 警告，不能成为阻断借口。
REQUIRED_ENVIRONMENT_KEYS = (
    "SystemDrive", "SystemRoot", "windir", "ProgramData", "ALLUSERSPROFILE",
    "USERPROFILE", "APPDATA", "LOCALAPPDATA", "TEMP", "TMP",
)
SAFE_EXTERNAL_RUNTIME_CWD = PureWindowsPath(r"D:\CadAgentRuntime\s5\launch")
_UNEXPANDED_VARIABLE = re.compile(r"%[^%]+%|\$\{[^}]+\}")


@dataclass(frozen=True)
class RealComLaunchPolicy:
    mode: ComBackendLaunchMode = "com_activation"
    external_runtime_cwd: str = str(SAFE_EXTERNAL_RUNTIME_CWD)

    def __post_init__(self) -> None:
        if self.mode not in {"com_activation", "process_launch"}:
            raise ValueError("Real COM launch mode 非法")


@dataclass(frozen=True)
class EnvironmentSanitization:
    environment: dict[str, str]
    warnings: tuple[dict[str, Any], ...]
    states: Mapping[str, str]


RPC_E_CALL_REJECTED = 0x80010001
RPC_E_SERVERCALL_RETRYLATER = 0x8001010A
_STARTUP_RETRY_HRESULTS = {RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER}


def _hresult(exception: Exception) -> int | None:
    value = getattr(exception, "hresult", None)
    candidates = (value, *getattr(exception, "args", ()))
    for candidate in candidates:
        if isinstance(candidate, int):
            return candidate & 0xFFFFFFFF
    return None


def read_with_startup_busy_retry(operation: Callable[[], Any], *, timeout_seconds: float = 45.0,
                                  interval_seconds: float = 0.5, clock: Callable[[], float] = monotonic,
                                  sleeper: Callable[[float], None] = sleep) -> Any:
    """仅为 DispatchEx 后的只读 COM identity 读取处理启动繁忙 HRESULT。"""
    if not 45.0 <= timeout_seconds <= 60.0 or not 0.5 <= interval_seconds <= 1.0:
        raise ValueError("S5 COM startup retry 必须使用 45–60 秒、0.5–1 秒边界")
    started = clock()
    while True:
        try:
            return operation()
        except Exception as exc:
            if _hresult(exc) not in _STARTUP_RETRY_HRESULTS:
                raise
            if clock() - started >= timeout_seconds:
                raise AutoCadLauncherError("AUTOCAD_COM_STARTUP_BUSY_TIMEOUT", "AutoCAD COM 启动繁忙超时") from exc
            sleeper(interval_seconds)


class EnvironmentValueState(str, Enum):
    PRESENT = "Present"
    RECOVERABLE = "Recoverable"
    INVALID = "Invalid"


class WindowsEnvironmentRecovery:
    """惰性 Windows 系统位置恢复；测试可注入，绝不回退到项目 cwd。"""

    def __init__(self, *, known_folder: Callable[[str], str | None] | None = None,
                 windows_directory: Callable[[], str | None] | None = None) -> None:
        self._known_folder = known_folder
        self._windows_directory = windows_directory

    def windows_directory(self) -> str | None:
        if self._windows_directory is not None:
            return self._windows_directory()
        try:
            from ctypes import create_unicode_buffer, windll
            buffer = create_unicode_buffer(32768)
            length = int(windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer)))
            return buffer.value if length else None
        except (ImportError, AttributeError, OSError):
            return None

    def known_folder(self, name: str) -> str | None:
        if self._known_folder is not None:
            return self._known_folder(name)
        # 使用 shell 已知文件夹 API；不读取用户文件内容。
        guids = {
            "ProgramData": "62AB5D82-FDC1-4DC3-A9DD-070D1D495D97",
            "Profile": "5E6C858F-0E22-4760-9AFE-EA3317B67173",
            "RoamingAppData": "3EB685DB-65F9-4CF6-A03A-E3EF65729F3D",
            "LocalAppData": "F1B32785-6FBA-4FCF-9D55-7B8E7F157091",
        }
        if name not in guids:
            return None
        try:
            from ctypes import POINTER, byref, c_wchar_p, windll
            from ctypes.wintypes import DWORD
            import uuid
            guid = uuid.UUID(guids[name]).bytes_le
            value = c_wchar_p()
            result = windll.shell32.SHGetKnownFolderPath(guid, DWORD(0), None, byref(value))
            if result != 0 or not value.value:
                return None
            try:
                return str(value.value)
            finally:
                windll.ole32.CoTaskMemFree(value)
        except (ImportError, AttributeError, OSError, ValueError):
            return None


def _expand(value: str, source: Mapping[str, str]) -> str:
    current = value
    for _ in range(8):
        expanded = re.sub(
            r"%([^%]+)%",
            lambda match: str(source.get(match.group(1), match.group(0))),
            current,
        )
        if expanded == current:
            return expanded
        current = expanded
    return current


def _reject_project_or_t_drive(path: PureWindowsPath) -> None:
    text = str(path).lower()
    if path.drive.lower() == "t:":
        raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", "禁止使用 T: 作为运行时环境回退")
    if "\\codexwork\\天正" in text:
        raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", "禁止使用项目目录作为运行时环境回退")


def sanitize_child_environment(source: Mapping[str, str] | None = None, *, recovery: WindowsEnvironmentRecovery | None = None) -> EnvironmentSanitization:
    """校验十项关键变量；缺失值仅可由受信任 Windows 来源恢复。"""
    values = {str(key): str(value) for key, value in (os.environ if source is None else source).items()}
    casefold_values = {key.casefold(): value for key, value in values.items()}
    normalized: dict[str, str] = {}
    warnings: list[dict[str, Any]] = []
    states: dict[str, str] = {}
    recovery = recovery or WindowsEnvironmentRecovery()

    def recover_value(key: str) -> tuple[str | None, str | None]:
        if key in {"SystemRoot", "windir"}:
            return recovery.windows_directory(), "GetWindowsDirectoryW"
        folders = {"ProgramData": "ProgramData", "ALLUSERSPROFILE": "ProgramData", "USERPROFILE": "Profile",
                   "APPDATA": "RoamingAppData", "LOCALAPPDATA": "LocalAppData"}
        if key in folders:
            return recovery.known_folder(folders[key]), "SHGetKnownFolderPath"
        if key in {"TEMP", "TMP"}:
            local = recovery.known_folder("LocalAppData")
            return (str(PureWindowsPath(local) / "Temp") if local else None), "SHGetKnownFolderPath:LocalAppData"
        return None, None

    # 首先处理 SystemRoot/windir，使后续 %SystemDrive% 可安全展开。
    for key in ("SystemRoot", "windir"):
        raw = casefold_values.get(key.casefold(), "").strip()
        mirrored_from = ""
        if not raw:
            sibling = "windir" if key == "SystemRoot" else "SystemRoot"
            sibling_raw = casefold_values.get(sibling.casefold(), "").strip()
            if sibling_raw:
                raw, mirrored_from = sibling_raw, sibling
        if raw:
            expanded = _expand(raw, values).strip()
            if _UNEXPANDED_VARIABLE.search(expanded):
                raw = ""
            else:
                path = PureWindowsPath(expanded)
                if not path.is_absolute():
                    states[key] = EnvironmentValueState.INVALID.value
                    raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", f"{key} 无法安全解析")
                _reject_project_or_t_drive(path)
                normalized[key] = str(path)
                states[key] = EnvironmentValueState.RECOVERABLE.value if mirrored_from else EnvironmentValueState.PRESENT.value
                if mirrored_from:
                    warnings.append({"name": key, "state": EnvironmentValueState.RECOVERABLE.value, "derived": mirrored_from})
                continue
        recovered, provider = recover_value(key)
        if not recovered:
            states[key] = EnvironmentValueState.INVALID.value
            raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", f"{key} 无法恢复")
        path = PureWindowsPath(recovered)
        if not path.is_absolute():
            states[key] = EnvironmentValueState.INVALID.value
            raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", f"{key} 恢复结果无效")
        _reject_project_or_t_drive(path)
        values[key], casefold_values[key.casefold()] = str(path), str(path)
        normalized[key], states[key] = str(path), EnvironmentValueState.RECOVERABLE.value
        warnings.append({"name": key, "state": EnvironmentValueState.RECOVERABLE.value, "derived": provider})

    raw_system_drive = casefold_values.get("systemdrive", "").strip()
    # 未展开的 token 不能作为盘符进入后续校验；它与缺失值同样只允许
    # 通过已验证的 SystemRoot/windir 恢复。
    if _UNEXPANDED_VARIABLE.search(_expand(raw_system_drive, values)):
        raw_system_drive = ""
        casefold_values["systemdrive"] = ""
    if not raw_system_drive:
        # SystemRoot/windir 必须先作为正常 critical path 通过等价校验；只从其
        # 已验证的绝对盘符推导 SystemDrive，绝不从 cwd、项目路径或 T: 猜测。
        derived_from = ""
        for candidate in ("SystemRoot", "windir"):
            raw_candidate = casefold_values.get(candidate.casefold(), "").strip()
            if not raw_candidate:
                continue
            expanded_candidate = _expand(raw_candidate, values).strip()
            if _UNEXPANDED_VARIABLE.search(expanded_candidate):
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED", f"环境变量未完全展开: {candidate}")
            candidate_path = PureWindowsPath(expanded_candidate)
            if not candidate_path.is_absolute():
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", f"{candidate} 必须为绝对路径")
            _reject_project_or_t_drive(candidate_path)
            if not re.fullmatch(r"[A-Za-z]:", candidate_path.drive):
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", f"{candidate} 无法提供有效盘符")
            casefold_values["systemdrive"] = candidate_path.drive.upper()
            values["SystemDrive"] = candidate_path.drive.upper()
            if candidate.casefold() == "windir" and not casefold_values.get("systemroot", "").strip():
                # Windows 的 windir/SystemRoot 在此受限场景中等价；仅在 windir
                # 已通过绝对路径、T:/项目拒绝后镜像，避免让 windir-only 环境
                # 在后续 critical loop 中再次退化为“缺 SystemRoot”。
                casefold_values["systemroot"] = expanded_candidate
                values["SystemRoot"] = expanded_candidate
                warnings.append({"name": "SystemRoot", "derived": "windir"})
            derived_from = candidate
            break
        if not derived_from:
            states["SystemDrive"] = EnvironmentValueState.INVALID.value
            raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", "SystemDrive 无法恢复")
        warnings.append({"name": "SystemDrive", "derived": derived_from})
        states["SystemDrive"] = EnvironmentValueState.RECOVERABLE.value
    for key in REQUIRED_ENVIRONMENT_KEYS:
        if key in normalized:
            continue
        raw = casefold_values.get(key.casefold(), "").strip()
        if not raw:
            recovered, provider = recover_value(key)
            if not recovered:
                states[key] = EnvironmentValueState.INVALID.value
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", f"{key} 无法恢复")
            raw = recovered
            warnings.append({"name": key, "state": EnvironmentValueState.RECOVERABLE.value, "derived": provider})
            states[key] = EnvironmentValueState.RECOVERABLE.value
        expanded = _expand(raw, values).strip()
        if _UNEXPANDED_VARIABLE.search(expanded):
            recovered, provider = recover_value(key)
            if not recovered:
                states[key] = EnvironmentValueState.INVALID.value
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE", f"{key} 无法恢复")
            expanded = recovered
            warnings.append({"name": key, "state": EnvironmentValueState.RECOVERABLE.value, "derived": provider})
            states[key] = EnvironmentValueState.RECOVERABLE.value
        if key == "SystemDrive":
            if not re.fullmatch(r"[A-Za-z]:", expanded):
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", "SystemDrive 必须是绝对盘符")
            path = PureWindowsPath(expanded + "\\")
            normalized[key] = expanded.upper()
        else:
            path = PureWindowsPath(expanded)
            if not path.is_absolute():
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", f"{key} 必须为绝对路径")
            normalized[key] = str(path)
            if key in {"TEMP", "TMP"} and "\\codexwork\\天正" in str(path).lower():
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", f"{key} 不得位于项目目录")
            if key in {"ProgramData", "ALLUSERSPROFILE"} and path.drive.lower() != "c:":
                raise AutoCadLauncherError("AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID", f"{key} 必须是系统路径")
        _reject_project_or_t_drive(path)
        states.setdefault(key, EnvironmentValueState.PRESENT.value)
    critical = {key.casefold() for key in REQUIRED_ENVIRONMENT_KEYS}
    for name, raw in values.items():
        if name.casefold() in critical:
            continue
        unresolved = _UNEXPANDED_VARIABLE.findall(_expand(raw, values))
        if unresolved:
            warnings.append({"name": name, "unresolved_tokens": unresolved})
    return EnvironmentSanitization(environment=normalized, warnings=tuple(warnings), states=states)


def normalize_child_environment(source: Mapping[str, str] | None = None, *, recovery: WindowsEnvironmentRecovery | None = None) -> dict[str, str]:
    """向后兼容入口：仅返回已验证的十项关键变量。"""
    return sanitize_child_environment(source, recovery=recovery).environment


def validate_external_runtime_cwd(value: str) -> Path:
    path = PureWindowsPath(value)
    if path != SAFE_EXTERNAL_RUNTIME_CWD:
        raise AutoCadLauncherError("AUTOCAD_LAUNCH_WORKING_DIRECTORY_UNSAFE", "仅允许受控外部运行目录")
    _reject_project_or_t_drive(path)
    return Path(str(path))


class ComActivationSessionHost:
    """带锁临时 cwd / sanitized environment 的 COM 独立激活宿主。"""

    _lock = RLock()

    def __init__(self, *, policy: RealComLaunchPolicy, environment: Mapping[str, str] | None = None) -> None:
        if policy.mode != "com_activation":
            raise AutoCadLauncherError("AUTOCAD_COM_ACTIVATION_REQUIRED", "Real COM Backend 仅允许 com_activation")
        self._runtime_cwd = validate_external_runtime_cwd(policy.external_runtime_cwd)
        sanitized = sanitize_child_environment(environment)
        self._environment = sanitized.environment
        self.environment_warnings = sanitized.warnings

    @contextmanager
    def activation_context(self) -> Iterator[None]:
        """仅在显式激活时临时切换，结束后恢复 cwd 与环境。"""
        with self._lock:
            previous_cwd = Path.cwd()
            previous = dict(os.environ)
            try:
                self._runtime_cwd.mkdir(parents=True, exist_ok=True)
                os.chdir(self._runtime_cwd)
                # 仅覆盖已校验的关键变量。清空整个环境会丢失 PATH、SystemRoot
                # 等 AutoCAD 运行所需的非关键变量，反而破坏安全启动的可预测性。
                os.environ.update(self._environment)
                yield
            finally:
                os.chdir(previous_cwd)
                os.environ.clear()
                os.environ.update(previous)


@dataclass(frozen=True)
class ProcessLaunchRuntime:
    """PROCESS_LAUNCH 专用 UI 运行时合同；不得用于 COM activation。"""

    environment: dict[str, str]
    working_directory: str

    @classmethod
    def create(cls, *, environment: Mapping[str, str] | None = None, working_directory: str = str(SAFE_EXTERNAL_RUNTIME_CWD)) -> "ProcessLaunchRuntime":
        return cls(
            environment=normalize_child_environment(environment),
            working_directory=str(validate_external_runtime_cwd(working_directory)),
        )


class IsolatedComActivator:
    """使用 injected client 的 DispatchEx 独立激活，拒绝普通 Dispatch。"""

    def __init__(self, *, client_importer: Callable[[], Any]) -> None:
        self._client_importer = client_importer

    def activate(self, progid: str) -> ComApplicationLike:
        try:
            client = self._client_importer()
        except ImportError as exc:
            raise AutoCadLauncherError("AUTOCAD_COM_DEPENDENCY_MISSING", "pywin32/win32com 不可用") from exc
        dispatch_ex = getattr(client, "DispatchEx", None)
        if not callable(dispatch_ex):
            raise AutoCadLauncherError("AUTOCAD_COM_ACTIVATION_UNAVAILABLE", "win32com client 不支持 DispatchEx")
        try:
            return dispatch_ex(progid)
        except Exception as exc:
            raise AutoCadLauncherError("AUTOCAD_COM_ACTIVATION_FAILED", "AutoCAD DispatchEx 独立激活失败") from exc

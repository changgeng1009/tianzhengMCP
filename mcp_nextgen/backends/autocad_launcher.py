"""S5 AutoCAD 进程启动安全边界。

本模块刻意不在 import 时导入 ``win32com``、不枚举真实进程，也不启动
AutoCAD。生产调用方必须显式注入进程检查器、COM 连接器和受审计的启动器；
单元测试仅使用 Fake 依赖验证 fail-closed 策略。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import csv
from io import StringIO
import os
from pathlib import Path
import re
import subprocess
from time import monotonic, sleep
from typing import Any, Callable, Literal, Mapping, Protocol, Sequence
from uuid import uuid4


LaunchMode = Literal["disabled", "launch_if_absent", "require_absent_then_launch"]


class AutoCadLauncherError(RuntimeError):
    """可审计的 Launcher 失败；调用方不得以 ActiveDocument 作为回退。"""

    def __init__(self, error_code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.details = details or {}


@dataclass(frozen=True)
class AutoCadLaunchPolicy:
    """不可由普通 Manifest 放宽的 S5 启动策略。"""

    mode: LaunchMode = "require_absent_then_launch"
    executable_path: str | None = None
    startup_timeout_seconds: float = 120.0
    poll_interval_seconds: float = 2.0
    attach_existing: bool = False
    allow_user_documents: bool = False
    quit_job_owned_instance: bool = True
    expected_version_prefix: str = "25"

    def __post_init__(self) -> None:
        if self.mode not in {"disabled", "launch_if_absent", "require_absent_then_launch"}:
            raise ValueError("autocad launch mode 非法")
        if self.mode == "require_absent_then_launch" and self.attach_existing:
            raise ValueError("require_absent_then_launch 禁止 attach_existing")
        if self.attach_existing or self.allow_user_documents:
            raise ValueError("S5 禁止 attach_existing 或 allow_user_documents")
        if self.startup_timeout_seconds <= 0 or self.poll_interval_seconds <= 0:
            raise ValueError("启动超时和轮询间隔必须大于 0")
        if not self.expected_version_prefix.strip():
            raise ValueError("expected_version_prefix 不能为空")


@dataclass(frozen=True)
class AutoCadProcessIdentity:
    job_id: str
    process_id: int
    executable_path: str
    process_start_time: float
    launched_by_job: bool
    ownership_token: str
    command_arguments: tuple[str, ...] = ()
    shell: bool = False
    os_verified_executable_path: str | None = None
    os_process_creation_filetime: int | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["command_arguments"] = list(self.command_arguments)
        return result


@dataclass(frozen=True)
class AutoCadSessionIdentity:
    job_id: str
    process: AutoCadProcessIdentity
    com_progid: str
    autocad_version: str
    document_count: int
    connected_at: float

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["process"] = self.process.to_dict()
        return result


@dataclass(frozen=True)
class LaunchResult:
    status: str
    process: AutoCadProcessIdentity
    session: AutoCadSessionIdentity | None = None
    launched: bool = False
    limitations: tuple[str, ...] = (
        "S5 仅允许 synthetic Sandbox；不得使用 ActiveDocument 作为回退。",
        "本结果不代表生产写入、天正或完整 Real Backend 可用。",
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "process": self.process.to_dict(),
            "session": None if self.session is None else self.session.to_dict(),
            "launched": self.launched,
            "limitations": list(self.limitations),
        }


class ProcessLike(Protocol):
    pid: int

    def poll(self) -> int | None: ...


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    executable_path: str
    started_at: float | None = None


class ComApplicationLike(Protocol):
    Version: str
    HWND: int

    @property
    def Documents(self) -> Any: ...


ProcessInspector = Callable[[], Sequence[ProcessSnapshot]]
PopenFactory = Callable[..., ProcessLike]
ComConnector = Callable[[str], ComApplicationLike]
PathExists = Callable[[Path], bool]
VersionReader = Callable[[Path], str]
HwndPidResolver = Callable[[int], int]
ProcessIdentityInspector = Callable[[AutoCadProcessIdentity], AutoCadProcessIdentity]


class WindowsProcessIdentityInspector:
    """在调用时用 Windows API 验证已启动 PID 的真实路径和创建时间。

    这是进程身份校验，不能替代 ownership token；它不枚举文档、不开 COM、
    不终止进程。测试可注入 ``query``，避免触发 Windows API。
    """

    def __init__(self, *, query: Callable[[int], tuple[str, int]] | None = None) -> None:
        self._query = query

    def __call__(self, identity: AutoCadProcessIdentity) -> AutoCadProcessIdentity:
        actual_path, creation_filetime = (self._query or self._query_windows)(identity.process_id)
        expected = Path(identity.executable_path).resolve(strict=False)
        actual = Path(actual_path).resolve(strict=False)
        if actual != expected:
            raise AutoCadLauncherError(
                "AUTOCAD_SESSION_UNSAFE",
                "OS 进程可执行路径与受信任 acad.exe 不匹配",
                details={"process_id": identity.process_id, "expected_path": str(expected), "actual_path": str(actual)},
            )
        if int(creation_filetime) <= 0:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "OS 未返回有效进程创建时间")
        return replace(
            identity,
            os_verified_executable_path=str(actual),
            os_process_creation_filetime=int(creation_filetime),
        )

    @staticmethod
    def _query_windows(process_id: int) -> tuple[str, int]:
        """延迟调用 Kernel32；不支持的平台和 API 错误均 fail-closed。"""
        try:
            from ctypes import WinDLL, byref, create_unicode_buffer, get_last_error, sizeof
            from ctypes.wintypes import DWORD, FILETIME, HANDLE

            kernel32 = WinDLL("kernel32", use_last_error=True)
            process = kernel32.OpenProcess(0x1000, False, int(process_id))  # PROCESS_QUERY_LIMITED_INFORMATION
            if not process:
                raise OSError(get_last_error(), "OpenProcess failed")
            try:
                size = DWORD(32768)
                buffer = create_unicode_buffer(size.value)
                if not kernel32.QueryFullProcessImageNameW(HANDLE(process), 0, buffer, byref(size)):
                    raise OSError(get_last_error(), "QueryFullProcessImageNameW failed")
                creation, _exit, _kernel, _user = FILETIME(), FILETIME(), FILETIME(), FILETIME()
                if not kernel32.GetProcessTimes(HANDLE(process), byref(creation), byref(_exit), byref(_kernel), byref(_user)):
                    raise OSError(get_last_error(), "GetProcessTimes failed")
                creation_value = (int(creation.dwHighDateTime) << 32) | int(creation.dwLowDateTime)
                return buffer.value, creation_value
            finally:
                kernel32.CloseHandle(HANDLE(process))
        except (ImportError, AttributeError, OSError) as exc:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "无法 OS 级验证 AutoCAD 进程身份") from exc


@dataclass(frozen=True)
class AutoCadDocumentSnapshot:
    """仅用于 Job-owned 新会话的只读 Document 安全检查。"""

    name: str
    full_name: str
    saved: bool
    read_only: bool
    dwg_titled: int
    dbmod: int
    cmdnames: str
    model_space_entity_count: int
    paper_space_non_default_entity_count: int

    @property
    def is_new_default_blank(self) -> bool:
        """仅允许已验证的默认空白 Drawing*.dwg 文档。

        新进程中的 AutoCAD 默认文档可能返回 ``Saved=True``，不能据此误判为
        用户图纸；因此以 DWGTITLED/DBMOD/CMDNAMES 和 Model/PaperSpace 的
        空白状态共同判定。``FullName`` 一旦非空仍一律阻断。
        """
        return (
            self.name.lower().startswith("drawing")
            and self.name.lower().endswith(".dwg")
            and not self.full_name
            and not self.read_only
            and self.dwg_titled == 0
            and self.dbmod == 0
            and not self.cmdnames.strip()
            and self.model_space_entity_count == 0
            and self.paper_space_non_default_entity_count == 0
        )


@dataclass(frozen=True)
class AutoCadSessionVerification:
    session: AutoCadSessionIdentity
    application_hwnd: int
    hwnd_process_id: int
    documents: tuple[AutoCadDocumentSnapshot, ...]

    @property
    def has_only_new_default_blank_documents(self) -> bool:
        return all(item.is_new_default_blank for item in self.documents)


@dataclass(frozen=True)
class SafeShutdownPlan:
    process_id: int
    job_id: str
    close_without_save_names: tuple[str, ...]
    quit_after_close: bool


class WindowsHwndPidResolver:
    """仅在调用时将已取得的 COM HWND 映射为 PID；模块导入没有 COM 副作用。"""

    def __init__(self, *, get_window_thread_process_id: Callable[[int], tuple[int, int]] | None = None) -> None:
        self._get_window_thread_process_id = get_window_thread_process_id

    def __call__(self, hwnd: int) -> int:
        if int(hwnd) <= 0:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "AutoCAD HWND 非法")
        if self._get_window_thread_process_id is None:
            try:
                from ctypes import byref, c_ulong, windll

                pid = c_ulong(0)
                _thread_id = windll.user32.GetWindowThreadProcessId(int(hwnd), byref(pid))
                resolved_pid = int(pid.value)
            except (ImportError, AttributeError) as exc:
                raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "无法取得 HWND 对应 PID") from exc
        else:
            _thread_id, resolved_pid = self._get_window_thread_process_id(int(hwnd))
        if int(resolved_pid) <= 0:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "HWND 未映射到有效 AutoCAD PID")
        return int(resolved_pid)


class WindowsAcadProcessInspector:
    """只读检测 ``acad.exe`` 进程。

    ``tasklist`` 的输出不用于建立所有权；只要发现任一同名进程即由上层
    fail-closed。命令固定、``shell=False``、不传入任何图纸路径，也不做
    关闭/保存/窗口操作。
    """

    def __init__(self, *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run) -> None:
        self._runner = runner

    def __call__(self) -> Sequence[ProcessSnapshot]:
        try:
            result = self._runner(
                ["tasklist", "/fo", "csv", "/nh", "/fi", "IMAGENAME eq acad.exe"],
                shell=False,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AutoCadLauncherError("AUTOCAD_PROCESS_INSPECTION_FAILED", "无法安全检查 acad.exe 进程") from exc
        if result.returncode != 0:
            raise AutoCadLauncherError("AUTOCAD_PROCESS_INSPECTION_FAILED", "tasklist 进程检查失败")
        records: list[ProcessSnapshot] = []
        for row in csv.reader(StringIO(result.stdout)):
            if len(row) < 2 or row[0].strip().lower() != "acad.exe":
                continue
            try:
                pid = int(row[1])
            except ValueError:
                # 任何难以解析的 acad.exe 记录均不能被当作“无进程”。
                raise AutoCadLauncherError("AUTOCAD_PROCESS_INSPECTION_FAILED", "acad.exe PID 无法解析")
            records.append(ProcessSnapshot(pid=pid, executable_path="<unknown-existing-acad.exe>"))
        return tuple(records)


class SafeAutoCadPopen:
    """将实际启动限制为已解析的单一 acad.exe 路径和 ``shell=False``。"""

    def __init__(
        self,
        *,
        factory: PopenFactory | None = None,
        sanitized_environment: Mapping[str, str] | None = None,
        working_directory: str | None = None,
    ) -> None:
        self._factory = factory or subprocess.Popen  # type: ignore[assignment]
        self._environment = None if sanitized_environment is None else dict(sanitized_environment)
        self._working_directory = working_directory
        if (self._environment is None) != (self._working_directory is None):
            raise AutoCadLauncherError(
                "AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED",
                "PROCESS_LAUNCH 必须同时提供 sanitized_env 与安全外部 cwd",
            )

    @classmethod
    def for_process_launch(
        cls,
        *,
        factory: PopenFactory | None = None,
        environment: Mapping[str, str] | None = None,
        working_directory: str | None = None,
    ) -> "SafeAutoCadPopen":
        """为 UI-only PROCESS_LAUNCH 创建显式外部 cwd/sanitized_env 契约。"""
        from .autocad_com_activation import ProcessLaunchRuntime

        runtime = ProcessLaunchRuntime.create(environment=environment, working_directory=working_directory or r"D:\CadAgentRuntime\s5\launch")
        return cls(factory=factory, sanitized_environment=runtime.environment, working_directory=runtime.working_directory)

    def __call__(self, args: Sequence[str], *, shell: bool) -> ProcessLike:
        values = tuple(str(item) for item in args)
        if shell or len(values) != 1 or Path(values[0]).name.lower() != "acad.exe":
            raise AutoCadLauncherError("AUTOCAD_LAUNCH_ARGUMENTS_INVALID", "启动参数必须是唯一受信任的 acad.exe 且 shell=false")
        if self._environment is None or self._working_directory is None:
            raise AutoCadLauncherError(
                "AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVED",
                "PROCESS_LAUNCH 未配置 sanitized_env 与安全外部 cwd",
            )
        kwargs: dict[str, Any] = {"shell": False}
        if self._environment is not None and self._working_directory is not None:
            kwargs["env"] = self._environment
            kwargs["cwd"] = self._working_directory
        return self._factory(list(values), **kwargs)  # type: ignore[call-arg]


class AutoCadProcessOwnershipRegistry:
    """进程所有权只由本 Job 启动结果登记，绝不按进程名称猜测。"""

    def __init__(self) -> None:
        self._records: dict[int, AutoCadProcessIdentity] = {}

    def register(self, identity: AutoCadProcessIdentity) -> None:
        prior = self._records.get(identity.process_id)
        if prior is not None and prior.ownership_token != identity.ownership_token:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "进程 PID 所有权冲突")
        self._records[identity.process_id] = identity

    def get(self, process_id: int) -> AutoCadProcessIdentity | None:
        return self._records.get(process_id)

    def belongs_to_job(self, *, process_id: int, job_id: str, ownership_token: str) -> bool:
        item = self.get(process_id)
        return bool(item and item.job_id == job_id and item.ownership_token == ownership_token and item.launched_by_job)

    def may_quit(self, session: AutoCadSessionIdentity, *, document_count: int) -> bool:
        """正常 Quit 的必要条件；不实际调用 Quit。"""
        process = session.process
        return self.belongs_to_job(
            process_id=process.process_id,
            job_id=session.job_id,
            ownership_token=process.ownership_token,
        ) and document_count == 0


class AutoCadJobOwnedSessionGuard:
    """对 Job-owned COM 会话作 HWND/PID 和默认空白文档的 fail-closed 审计。"""

    def __init__(self, *, ownership: AutoCadProcessOwnershipRegistry, hwnd_pid_resolver: HwndPidResolver) -> None:
        self._ownership = ownership
        self._hwnd_pid_resolver = hwnd_pid_resolver

    def verify(self, session: AutoCadSessionIdentity, application: ComApplicationLike) -> AutoCadSessionVerification:
        hwnd = int(application.HWND)
        mapped_pid = self._hwnd_pid_resolver(hwnd)
        if mapped_pid != session.process.process_id or not self._ownership.belongs_to_job(
            process_id=mapped_pid,
            job_id=session.job_id,
            ownership_token=session.process.ownership_token,
        ):
            raise AutoCadLauncherError(
                "AUTOCAD_SESSION_UNSAFE",
                "COM HWND/PID 与当前 Job-owned 进程不匹配",
                details={"hwnd": hwnd, "mapped_pid": mapped_pid, "expected_pid": session.process.process_id},
            )
        documents = tuple(self._snapshot_documents(application.Documents))
        return AutoCadSessionVerification(session, hwnd, mapped_pid, documents)

    def plan_safe_shutdown(self, verification: AutoCadSessionVerification) -> SafeShutdownPlan:
        """仅生成 Close(False)/Quit 计划，不调用 Close 或 Quit。"""
        if not verification.has_only_new_default_blank_documents:
            raise AutoCadLauncherError(
                "AUTOCAD_USER_DOCUMENT_PROTECTION_TRIGGERED",
                "会话存在非默认空白或已保存文档；不得关闭或退出",
                details={"documents": [asdict(item) for item in verification.documents]},
            )
        process = verification.session.process
        if not self._ownership.belongs_to_job(
            process_id=process.process_id,
            job_id=verification.session.job_id,
            ownership_token=process.ownership_token,
        ):
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "关闭前进程所有权无法验证")
        return SafeShutdownPlan(
            process_id=process.process_id,
            job_id=verification.session.job_id,
            close_without_save_names=tuple(item.name for item in verification.documents),
            quit_after_close=True,
        )

    @staticmethod
    def _snapshot_documents(documents: Any) -> list[AutoCadDocumentSnapshot]:
        try:
            iterable = list(documents)
        except TypeError as exc:
            raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "无法只读枚举当前 Documents") from exc
        snapshots: list[AutoCadDocumentSnapshot] = []
        for document in iterable:
            try:
                snapshots.append(
                    AutoCadDocumentSnapshot(
                        name=str(document.Name),
                        full_name=str(document.FullName or ""),
                        saved=bool(document.Saved),
                        read_only=bool(document.ReadOnly),
                        dwg_titled=int(document.GetVariable("DWGTITLED")),
                        dbmod=int(document.GetVariable("DBMOD")),
                        cmdnames=str(document.GetVariable("CMDNAMES") or ""),
                        model_space_entity_count=int(document.ModelSpace.Count),
                        paper_space_non_default_entity_count=sum(
                            1
                            for entity in document.PaperSpace
                            if str(entity.ObjectName) not in {"AcDbViewport"}
                        ),
                    )
                )
            except Exception as exc:
                raise AutoCadLauncherError("AUTOCAD_SESSION_UNSAFE", "无法读取 Document 安全身份") from exc
        return snapshots


class AutoCadExecutableResolver:
    """只接受已知安装根下、精确命名为 acad.exe 的路径。"""

    def __init__(
        self,
        *,
        allowed_install_root: Path = Path(r"E:\AutoCAD 2026"),
        path_exists: PathExists | None = None,
        version_reader: VersionReader | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._root = allowed_install_root.resolve(strict=False)
        self._path_exists = path_exists or Path.exists
        self._version_reader = version_reader
        self._environment = {str(key): str(value) for key, value in (os.environ if environment is None else environment).items()}

    def resolve(self, explicit_path: str | None = None) -> Path:
        candidate = self._expand_explicit_path(explicit_path) if explicit_path else self._root / "acad.exe"
        if not candidate.is_absolute():
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_NOT_ABSOLUTE", "acad.exe 路径必须为绝对路径")
        canonical = candidate.resolve(strict=False)
        if not canonical.is_absolute():
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_NOT_ABSOLUTE", "acad.exe 路径必须为绝对路径")
        if canonical.drive.lower() == "t:" or "\\codexwork\\天正" in str(canonical).lower():
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_FORBIDDEN_FALLBACK", "禁止项目目录或 T: 作为 acad.exe 回退路径")
        if canonical.name.lower() != "acad.exe":
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_INVALID", "可执行文件必须为 acad.exe")
        try:
            canonical.relative_to(self._root)
        except ValueError as exc:
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_INVALID", "acad.exe 路径超出受信任安装目录") from exc
        if not self._path_exists(canonical):
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_NOT_FOUND", f"未找到 acad.exe: {canonical}")
        if self._version_reader is not None:
            version = self._version_reader(canonical)
            if not str(version).startswith("25"):
                raise AutoCadLauncherError("AUTOCAD_VERSION_MISMATCH", f"AutoCAD 版本不属于 2026 COM 主版本: {version}")
        return canonical

    def _expand_explicit_path(self, value: str) -> Path:
        current = str(value).strip()
        if not current:
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_INVALID", "AUTOCAD_EXE_PATH 不能为空")
        for _ in range(8):
            updated = re.sub(
                r"%([^%]+)%",
                lambda match: self._environment.get(match.group(1), match.group(0)),
                current,
            )
            if updated == current:
                break
            current = updated
        if re.search(r"%[^%]+%|\$\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*", current):
            raise AutoCadLauncherError("AUTOCAD_EXECUTABLE_PATH_UNEXPANDED", "AUTOCAD_EXE_PATH 包含未展开变量")
        return Path(current).expanduser()


class AutoCadProcessLauncher:
    """进程启动合同；Real COM 不得使用其 COM 等待路径。

    新代码应调用 :meth:`launch_process_only`，该方法绝不调用 COM connector。
    ``launch`` 仅保留给既有纯 Mock 兼容测试，不是 Real COM Backend 接口。
    """

    def __init__(
        self,
        *,
        policy: AutoCadLaunchPolicy,
        process_inspector: ProcessInspector,
        popen: PopenFactory,
        com_connector: ComConnector,
        resolver: AutoCadExecutableResolver,
        ownership: AutoCadProcessOwnershipRegistry | None = None,
        process_identity_inspector: ProcessIdentityInspector | None = None,
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self.policy = policy
        self._process_inspector = process_inspector
        self._popen = popen
        self._com_connector = com_connector
        self._resolver = resolver
        self.ownership = ownership or AutoCadProcessOwnershipRegistry()
        self._process_identity_inspector = process_identity_inspector
        self._clock = clock
        self._sleeper = sleeper

    def launch_process_only(self, *, job_id: str) -> LaunchResult:
        """PROCESS_LAUNCH 合同：只创建 Job-owned 进程，绝不连接 COM。"""
        if not isinstance(self._popen, SafeAutoCadPopen):
            raise AutoCadLauncherError(
                "AUTOCAD_LAUNCH_WORKING_DIRECTORY_UNSAFE",
                "PROCESS_LAUNCH 必须使用配置了外部 cwd/sanitized_env 的 SafeAutoCadPopen",
            )
        identity, _process = self._launch_process_only(job_id=job_id)
        return LaunchResult(status="PROCESS_STARTED", process=identity, session=None, launched=True)

    def _launch_process_only(self, *, job_id: str) -> tuple[AutoCadProcessIdentity, ProcessLike]:
        if not job_id:
            raise ValueError("job_id 不能为空")
        if self.policy.mode == "disabled":
            raise AutoCadLauncherError("AUTOCAD_LAUNCH_DISABLED", "当前 launch policy=disabled")
        existing = tuple(self._process_inspector())
        if existing:
            raise AutoCadLauncherError(
                "EXISTING_PROCESS_UNKNOWN_OWNER",
                "发现既有 acad.exe；S5 禁止附着或操作其文档",
                details={"processes": [item.pid for item in existing]},
            )
        executable = self._resolver.resolve(self.policy.executable_path)
        process = self._popen([str(executable)], shell=False)
        process_id = int(process.pid)
        identity = AutoCadProcessIdentity(
            job_id=job_id,
            process_id=process_id,
            executable_path=str(executable),
            process_start_time=self._clock(),
            launched_by_job=True,
            ownership_token=uuid4().hex,
            command_arguments=(),
            shell=False,
        )
        if self._process_identity_inspector is not None:
            identity = self._process_identity_inspector(identity)
        self.ownership.register(identity)
        return identity, process

    def launch(self, *, job_id: str, com_progid: str) -> LaunchResult:
        """历史 Mock 兼容入口；S5 Real COM 必须改用 COM_ACTIVATION。"""
        if not job_id or not com_progid:
            raise ValueError("job_id 与 com_progid 不能为空")
        identity, process = self._launch_process_only(job_id=job_id)
        session = self._wait_for_com(process, identity, com_progid)
        return LaunchResult(status="COM_READY", process=identity, session=session, launched=True)

    def _wait_for_com(
        self,
        process: ProcessLike,
        identity: AutoCadProcessIdentity,
        com_progid: str,
    ) -> AutoCadSessionIdentity:
        deadline = self._clock() + self.policy.startup_timeout_seconds
        last_error: Exception | None = None
        while self._clock() <= deadline:
            if process.poll() is not None:
                raise AutoCadLauncherError(
                    "AUTOCAD_PROCESS_EXITED_DURING_STARTUP",
                    "acad.exe 在 COM 就绪前退出",
                    details={"process_id": identity.process_id},
                )
            try:
                application = self._com_connector(com_progid)
                version = str(application.Version)
                if not version.startswith(self.policy.expected_version_prefix):
                    raise AutoCadLauncherError("AUTOCAD_VERSION_MISMATCH", f"COM Version 不匹配: {version}")
                count = int(application.Documents.Count)
                return AutoCadSessionIdentity(
                    job_id=identity.job_id,
                    process=identity,
                    com_progid=com_progid,
                    autocad_version=version,
                    document_count=count,
                    connected_at=self._clock(),
                )
            except AutoCadLauncherError:
                raise
            except Exception as exc:  # COM server 尚未 ready 的可重试边界
                last_error = exc
                self._sleeper(self.policy.poll_interval_seconds)
        raise AutoCadLauncherError(
            "AUTOCAD_COM_NOT_READY",
            "AutoCAD COM 在启动超时内未就绪",
            details={"process_id": identity.process_id, "last_error": None if last_error is None else type(last_error).__name__},
        )


class LazyAutoCadComTransport:
    """按需导入 pywin32 的传输适配器；模块导入本身没有 COM 副作用。

    ``client_importer`` 供默认安全测试注入 ``ImportError`` 或纯 Fake client，
    避免测试为验证依赖缺失而触发实际 COM import。默认 importer 仅在显式
    ``connect()`` 调用时解析 ``win32com.client``。
    """

    def __init__(self, *, client_importer: Callable[[], Any] | None = None) -> None:
        self._client_importer = client_importer or self._default_client_importer

    @staticmethod
    def _default_client_importer() -> Any:
        from importlib import import_module

        return import_module("win32com.client")

    def _client(self) -> Any:
        try:
            return self._client_importer()
        except ImportError as exc:
            raise AutoCadLauncherError("AUTOCAD_COM_DEPENDENCY_MISSING", "pywin32/win32com 不可用") from exc

    def activate_isolated(self, progid: str) -> ComApplicationLike:
        """S5 Real COM 的默认路径：只允许 DispatchEx 独立激活。"""
        client = self._client()
        dispatch_ex = getattr(client, "DispatchEx", None)
        if not callable(dispatch_ex):
            raise AutoCadLauncherError("AUTOCAD_COM_ACTIVATION_UNAVAILABLE", "win32com client 不支持 DispatchEx")
        try:
            return dispatch_ex(progid)
        except Exception as exc:
            raise AutoCadLauncherError("AUTOCAD_COM_ACTIVATION_FAILED", "无法通过 DispatchEx 独立激活 AutoCAD") from exc

    def connect(self, progid: str) -> ComApplicationLike:
        """兼容入口仍使用独立激活，禁止普通 Dispatch / GetActiveObject 回退。"""
        return self.activate_isolated(progid)

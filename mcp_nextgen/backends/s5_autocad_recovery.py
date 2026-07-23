"""S5 开发环境的精确 PID AutoCAD 恢复助手。

此模块不在 import 时连接 COM、不枚举或终止进程。恢复默认关闭，且只接受
当前 S5 evidence 已绑定的单一 Job-owned PID。它不是生产恢复机制，也不能
用于用户 DWG、未知会话或批量进程操作。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic, sleep
from typing import Any, Callable, Mapping, Protocol

from .autocad_com_activation import read_with_startup_busy_retry
from .autocad_launcher import AutoCadProcessIdentity, WindowsProcessIdentityInspector


# S5 开发恢复只能由这一个用户授权环境门显式开启；不接受历史兼容变量。
DEVELOPMENT_RECOVERY_ENV = "CAD_S5_DEVELOPMENT_AUTORECOVERY"


class RecoveryApplication(Protocol):
    HWND: int

    @property
    def Documents(self) -> Any: ...

    def Quit(self) -> None: ...


@dataclass(frozen=True)
class RecoveryEvidence:
    """调用者已解析的 S5 evidence，绝不在此模块中跟随读取文件。"""

    run_id: str
    job_id: str
    process_id: int
    ownership_token: str
    expected_executable_path: str
    process_creation_filetime: int
    synthetic_document_path: str
    artifact_root: str
    hwnd: int | None = None
    launch_strategy: str = "COM_ACTIVATION"
    launched_by_job: bool = True

    def validate(self) -> str | None:
        root = Path(self.artifact_root).resolve(strict=False)
        synthetic = Path(self.synthetic_document_path).resolve(strict=False)
        if not self.run_id or not self.job_id or self.process_id <= 0 or not self.ownership_token:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.launch_strategy != "COM_ACTIVATION" or not self.launched_by_job:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.process_creation_filetime <= 0 or Path(self.expected_executable_path).name.lower() != "acad.exe":
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if synthetic.suffix.lower() != ".dwg" or synthetic.parent != (root / "sandbox").resolve(strict=False):
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.hwnd is not None and self.hwnd <= 0:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        return None


@dataclass(frozen=True)
class RecoveryEvidenceDev:
    """启动前失败时的开发恢复证据。

    此分支用于尚未创建 synthetic DWG、因此没有 document token 的 S5 run。
    它只能由用户明确的“无人工文档”开发声明启用，并要求 PID、可执行路径、
    OS 创建 FILETIME、run 窗口与已有失败 evidence 的 PID 链接共同匹配。
    """

    run_id: str
    job_id: str
    process_id: int
    expected_executable_path: str
    run_window_start_filetime: int
    run_window_end_filetime: int
    evidence_process_id: int
    user_no_manual_docs: bool
    user_confirmed_exact_pid_force: bool = False
    baseline_process_ids: tuple[int, ...] = ()
    hwnd: int | None = None
    launch_strategy: str = "COM_ACTIVATION"

    def validate(self) -> str | None:
        if not self.run_id or not self.job_id or self.process_id <= 0:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.launch_strategy != "COM_ACTIVATION" or not self.user_no_manual_docs:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.evidence_process_id != self.process_id or self.process_id in set(self.baseline_process_ids):
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.run_window_start_filetime <= 0 or self.run_window_end_filetime < self.run_window_start_filetime:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if Path(self.expected_executable_path).name.lower() != "acad.exe":
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        if self.hwnd is not None and self.hwnd <= 0:
            return "S5_RECOVERY_EVIDENCE_MISMATCH"
        return None


@dataclass(frozen=True)
class RecoveryPolicy:
    """开发恢复的不可放宽边界；force 默认关闭且需明确调用方策略。"""

    development_env_var: str = DEVELOPMENT_RECOVERY_ENV
    # True 表示调用方已带入用户的单次 force 授权；它仍必须先通过同一
    # CAD_S5_DEVELOPMENT_AUTORECOVERY 环境门和 exact PID 证据匹配。
    allow_force_termination: bool = False
    timeout_seconds: float = 45.0
    interval_seconds: float = 0.5


@dataclass(frozen=True)
class RecoveryResult:
    status: str
    error_code: str | None
    error_stage: str | None
    operations: tuple[str, ...]
    process_ids: tuple[int, ...]
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "error_code": self.error_code,
            "error_stage": self.error_stage,
            "operations": list(self.operations),
            "process_ids": list(self.process_ids),
            "warnings": list(self.warnings),
        }


RotConnector = Callable[[str], RecoveryApplication]
HwndPidResolver = Callable[[int], int]
PidExists = Callable[[int], bool]
NormalWindowCloser = Callable[[int], bool]
ForceTerminator = Callable[[int], bool]
ProcessIdentityInspector = Callable[[AutoCadProcessIdentity], AutoCadProcessIdentity]
CimCreationTimeProvider = Callable[[int], int | None]
ExactPidWindowResolver = Callable[[int], int | None]
ProcessImageNameProvider = Callable[[int], str | None]


class WindowsExactPidTopLevelWindowResolver:
    """只解析一个精确 PID 的可见、无 owner 顶级窗口。

    返回 ``None`` 表示零个或多个候选，调用方必须 fail-closed。它不读取标题、
    不枚举/关闭其他 PID，也不发送任何窗口消息。
    """

    GW_OWNER = 4

    def __init__(
        self,
        *,
        enumerate_windows: Callable[[Callable[[int], bool]], bool] | None = None,
        is_visible: Callable[[int], bool] | None = None,
        owner_of: Callable[[int], int] | None = None,
        pid_of: Callable[[int], int] | None = None,
    ) -> None:
        self._enumerate_windows = enumerate_windows
        self._is_visible = is_visible
        self._owner_of = owner_of
        self._pid_of = pid_of

    def __call__(self, exact_pid: int) -> int | None:
        candidates: list[int] = []

        def collect(hwnd: int) -> bool:
            try:
                if self._visible(hwnd) and self._owner(hwnd) == 0 and self._pid(hwnd) == int(exact_pid):
                    candidates.append(int(hwnd))
            except Exception:
                return True
            return True

        try:
            if self._enumerate_windows is not None:
                self._enumerate_windows(collect)
            else:
                self._enum_windows_native(collect)
        except Exception:
            return None
        return candidates[0] if len(candidates) == 1 else None

    def _visible(self, hwnd: int) -> bool:
        if self._is_visible is not None:
            return bool(self._is_visible(hwnd))
        from ctypes import WinDLL

        return bool(WinDLL("user32", use_last_error=True).IsWindowVisible(int(hwnd)))

    def _owner(self, hwnd: int) -> int:
        if self._owner_of is not None:
            return int(self._owner_of(hwnd))
        from ctypes import WinDLL

        return int(WinDLL("user32", use_last_error=True).GetWindow(int(hwnd), self.GW_OWNER) or 0)

    def _pid(self, hwnd: int) -> int:
        if self._pid_of is not None:
            return int(self._pid_of(hwnd))
        from ctypes import WinDLL, byref
        from ctypes.wintypes import DWORD

        process_id = DWORD(0)
        WinDLL("user32", use_last_error=True).GetWindowThreadProcessId(int(hwnd), byref(process_id))
        return int(process_id.value)

    @staticmethod
    def _enum_windows_native(callback: Callable[[int], bool]) -> None:
        from ctypes import WINFUNCTYPE, WinDLL
        from ctypes.wintypes import BOOL, HWND, LPARAM

        user32 = WinDLL("user32", use_last_error=True)
        procedure_type = WINFUNCTYPE(BOOL, HWND, LPARAM)

        @procedure_type
        def procedure(hwnd: int, _lparam: int) -> bool:
            return bool(callback(int(hwnd)))

        user32.EnumWindows(procedure, 0)


class S5AutoCadRecovery:
    """只恢复 evidence 与 OS/COM 身份三方一致的单一 S5 会话。

    `force_terminator` 必须由调用方明确注入。模块没有 taskkill、PowerShell
    或批量终止实现，因而不能误伤同名/未知 AutoCAD 进程。
    """

    def __init__(
        self,
        *,
        rot_connector: RotConnector,
        hwnd_pid_resolver: HwndPidResolver,
        pid_exists: PidExists,
        normal_window_closer: NormalWindowCloser,
        process_identity_inspector: ProcessIdentityInspector | None = None,
        cim_creation_time_provider: CimCreationTimeProvider | None = None,
        exact_pid_window_resolver: ExactPidWindowResolver | None = None,
        process_image_name_provider: ProcessImageNameProvider | None = None,
        force_terminator: ForceTerminator | None = None,
        policy: RecoveryPolicy = RecoveryPolicy(),
        clock: Callable[[], float] = monotonic,
        sleeper: Callable[[float], None] = sleep,
    ) -> None:
        self._rot_connector = rot_connector
        self._hwnd_pid_resolver = hwnd_pid_resolver
        self._pid_exists = pid_exists
        self._normal_window_closer = normal_window_closer
        self._inspect_identity = process_identity_inspector or WindowsProcessIdentityInspector()
        self._cim_creation_time_provider = cim_creation_time_provider
        self._exact_pid_window_resolver = exact_pid_window_resolver
        self._process_image_name_provider = process_image_name_provider
        self._force_terminator = force_terminator
        self._policy = policy
        self._clock = clock
        self._sleeper = sleeper

    def recover(
        self,
        *,
        evidence: RecoveryEvidence | RecoveryEvidenceDev,
        environment: Mapping[str, str],
        progid: str = "AutoCAD.Application.25.1",
    ) -> RecoveryResult:
        operations: list[str] = []
        pid = int(evidence.process_id)
        if environment.get(self._policy.development_env_var) != "1":
            return self._result("BLOCKED", "S5_DEVELOPMENT_RECOVERY_DISABLED", "DEVELOPMENT_GATE", operations, pid)
        if isinstance(evidence, RecoveryEvidenceDev):
            return self._recover_dev_startup_failure(evidence, environment, progid, operations)
        mismatch = evidence.validate()
        if mismatch:
            return self._result("BLOCKED", mismatch, "EVIDENCE_MATCH", operations, pid)
        operations.append("evidence_validated")
        if not self._pid_exists(pid):
            return self._result("BLOCKED", "AUTOCAD_RECOVERY_TARGET_NOT_RUNNING", "PROCESS_PRECHECK", operations, pid)
        identity = AutoCadProcessIdentity(
            job_id=evidence.job_id,
            process_id=pid,
            executable_path=str(Path(evidence.expected_executable_path).resolve(strict=False)),
            process_start_time=self._clock(),
            launched_by_job=True,
            ownership_token=evidence.ownership_token,
        )
        try:
            verified = self._inspect_identity(identity)
        except Exception:
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "OS_PROCESS_IDENTITY", operations, pid)
        if not self._verified_executable_matches(verified, evidence.expected_executable_path):
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "OS_PROCESS_EXECUTABLE", operations, pid)
        if verified.os_process_creation_filetime != evidence.process_creation_filetime:
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "PROCESS_CREATION_TIME", operations, pid)
        operations.append("os_identity_verified")

        try:
            application = self._rot_connector(progid)
            operations.append("rot_connected")
            hwnd = self._call_with_busy_retry(lambda: int(application.HWND))
            if self._hwnd_pid_resolver(hwnd) != pid:
                return self._result("BLOCKED", "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "ROT_HWND_PID", operations, pid)
            operations.append("rot_pid_verified")
            documents = tuple(application.Documents)
            if not self._only_registered_synthetic(documents, evidence.synthetic_document_path):
                return self._result("BLOCKED", "AUTOCAD_DOCUMENT_IDENTITY_MISMATCH", "DOCUMENT_SCOPE", operations, pid)
            for document in documents:
                self._call_with_busy_retry(lambda document=document: document.Close(False))
            if int(self._call_with_busy_retry(lambda: application.Documents.Count)) != 0:
                return self._result("FAILED", "AUTOCAD_RECOVERY_DOCUMENT_CLOSE_FAILED", "DOCUMENT_CLOSE", operations, pid)
            operations.append("synthetic_document_closed")
            self._call_with_busy_retry(application.Quit)
            operations.append("application_quit")
            if not self._wait_until_stopped(pid):
                return self._attempt_window_then_force(evidence, environment, operations, pid, hwnd)
            return self._result("RECOVERED_COM_ROT", None, None, operations, pid)
        except Exception:
            # ROT 未连接、启动仍 busy 或正常 COM Quit 失败时，不能猜测其他 PID；
            # 仅对之前通过 OS/evidence 匹配的同一 PID 走正常窗口关闭兜底。
            return self._attempt_window_then_force(evidence, environment, operations, pid, evidence.hwnd)

    @staticmethod
    def _only_registered_synthetic(documents: tuple[Any, ...], expected_path: str) -> bool:
        expected = Path(expected_path).resolve(strict=False)
        for document in documents:
            actual = Path(str(getattr(document, "FullName", "") or "")).resolve(strict=False)
            if actual != expected:
                return False
        return True

    def _recover_dev_startup_failure(
        self,
        evidence: RecoveryEvidenceDev,
        environment: Mapping[str, str],
        progid: str,
        operations: list[str],
    ) -> RecoveryResult:
        pid = evidence.process_id
        mismatch = evidence.validate()
        if mismatch:
            return self._result("BLOCKED", mismatch, "DEV_EVIDENCE_MATCH", operations, pid)
        operations.append("dev_evidence_validated")
        if not self._pid_exists(pid):
            return self._result("BLOCKED", "AUTOCAD_RECOVERY_TARGET_NOT_RUNNING", "PROCESS_PRECHECK", operations, pid)
        os_exact = self._dev_process_matches(evidence)
        cim_creation_verified = False
        if not os_exact:
            cim_creation_verified = self._dev_cim_creation_matches(evidence)
        if not os_exact and not cim_creation_verified:
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "OS_PROCESS_IDENTITY", operations, pid)
        operations.append("os_identity_verified" if os_exact else "cim_creation_window_verified")
        # ROT HWND 一旦读取并精确映射，后续 Close/Count/Quit 失败也必须沿用
        # 该已验证 HWND；不得退回 evidence 中可能为空的历史字段。
        current_hwnd = evidence.hwnd
        try:
            application = self._rot_connector(progid)
            operations.append("rot_connected")
            current_hwnd = self._call_with_busy_retry(lambda: int(application.HWND))
            if self._hwnd_pid_resolver(current_hwnd) != pid:
                return self._result("BLOCKED", "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "ROT_HWND_PID", operations, pid)
            operations.append("rot_pid_verified")
            if not os_exact:
                if not self._application_identity_matches(application, evidence.expected_executable_path):
                    return self._result("BLOCKED", "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "COM_APPLICATION_IDENTITY", operations, pid)
                operations.append("COM_VERIFIED_OS_INSPECTION_UNAVAILABLE")
            # 本分支仅因 evidence 明确表示启动前失败、未创建 synthetic 且用户
            # 已声明不存在人工文档，才允许 Close(False) 全部当前文档。
            for document in tuple(application.Documents):
                self._call_with_busy_retry(lambda document=document: document.Close(False))
            if int(self._call_with_busy_retry(lambda: application.Documents.Count)) != 0:
                return self._result("FAILED", "AUTOCAD_RECOVERY_DOCUMENT_CLOSE_FAILED", "DEV_DOCUMENT_CLOSE", operations, pid)
            operations.append("declared_dev_documents_closed")
            self._call_with_busy_retry(application.Quit)
            operations.append("application_quit")
            if self._wait_until_stopped(pid):
                return self._result("RECOVERED_COM_ROT", None, None, operations, pid)
            return self._attempt_dev_window_then_force(evidence, environment, operations, current_hwnd, os_exact=os_exact)
        except Exception:
            if current_hwnd is None and not os_exact and self._dev_cim_creation_matches(evidence):
                current_hwnd = self._resolve_exact_dev_hwnd(evidence.process_id, operations)
            return self._attempt_dev_window_then_force(evidence, environment, operations, current_hwnd, os_exact=os_exact)

    def _attempt_dev_window_then_force(
        self,
        evidence: RecoveryEvidenceDev,
        environment: Mapping[str, str],
        operations: list[str],
        hwnd: int | None,
        *,
        os_exact: bool,
    ) -> RecoveryResult:
        pid = evidence.process_id
        if os_exact and not self._dev_process_matches(evidence):
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "FALLBACK_PROCESS_REVERIFY", operations, pid)
        try:
            hwnd_matches = hwnd is not None and hwnd > 0 and self._hwnd_pid_resolver(hwnd) == pid
        except Exception:
            hwnd_matches = False
        if hwnd is None:
            # 无 ROT/顶级窗口候选时不猜测 HWND；其后只可能进入显式用户确认的
            # exact-PID 开发 force 收束。
            operations.append("normal_window_close_unavailable")
        elif not hwnd_matches:
            return self._result("BLOCKED", "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "FALLBACK_HWND_PID", operations, pid)
        else:
            try:
                normal_close_started = bool(self._normal_window_closer(hwnd))
            except Exception:
                normal_close_started = False
            if normal_close_started:
                operations.append("normal_window_close")
                if self._wait_until_stopped(pid):
                    return self._result("RECOVERED_WINDOW_CLOSE", None, None, operations, pid)
            else:
                operations.append("normal_window_close_failed")
        if not self._policy.allow_force_termination:
            return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_NOT_AUTHORIZED", "FORCE_GATE", operations, pid)
        warning: tuple[str, ...] = ("AUTOCAD_JOB_OWNED_PROCESS_FORCE_RECOVERED",)
        if os_exact:
            # force 之前再次验证 exact path + filetime run window + baseline exclusion。
            if not self._dev_process_matches(evidence):
                return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "FORCE_PROCESS_REVERIFY", operations, pid)
        elif not self._user_confirmed_dev_force_matches(evidence):
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "USER_CONFIRMED_DEV_FORCE_EVIDENCE", operations, pid)
        else:
            warning = ("AUTOCAD_USER_CONFIRMED_EXACT_PID_DEV_FORCE_RECOVERED",)
        try:
            force_started = self._force_terminator is not None and bool(self._force_terminator(pid))
        except Exception:
            force_started = False
        if not force_started:
            return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_FAILED", "FORCE_EXACT_PID", operations, pid)
        operations.append("force_exact_pid")
        if self._wait_until_stopped(pid):
            return self._result(
                "RECOVERED_FORCE_EXACT_PID", None, None, operations, pid,
                warnings=warning,
            )
        return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_FAILED", "FORCE_EXACT_PID", operations, pid)

    def _dev_process_matches(self, evidence: RecoveryEvidenceDev) -> bool:
        if not self._pid_exists(evidence.process_id):
            return False
        try:
            verified = self._inspect_identity(
                AutoCadProcessIdentity(
                    job_id=evidence.job_id,
                    process_id=evidence.process_id,
                    executable_path=str(Path(evidence.expected_executable_path).resolve(strict=False)),
                    process_start_time=self._clock(),
                    launched_by_job=True,
                    ownership_token="dev-recovery-evidence-only",
                )
            )
        except Exception:
            return False
        if not self._verified_executable_matches(verified, evidence.expected_executable_path):
            return False
        created = int(verified.os_process_creation_filetime or 0)
        return evidence.run_window_start_filetime <= created <= evidence.run_window_end_filetime

    def _dev_cim_creation_matches(self, evidence: RecoveryEvidenceDev) -> bool:
        if self._cim_creation_time_provider is None or not self._pid_exists(evidence.process_id):
            return False
        try:
            created = self._cim_creation_time_provider(evidence.process_id)
        except Exception:
            return False
        return bool(created and evidence.run_window_start_filetime <= int(created) <= evidence.run_window_end_filetime)

    def _resolve_exact_dev_hwnd(self, process_id: int, operations: list[str]) -> int | None:
        if self._exact_pid_window_resolver is None:
            return None
        try:
            hwnd = self._exact_pid_window_resolver(process_id)
        except Exception:
            return None
        if hwnd is not None:
            operations.append("exact_pid_top_level_hwnd_resolved")
        return hwnd

    def _application_identity_matches(self, application: RecoveryApplication, expected_executable_path: str) -> bool:
        try:
            version = str(self._call_with_busy_retry(lambda: str(getattr(application, "Version"))))
            application_path = self._call_with_busy_retry(lambda: str(getattr(application, "Path")))
        except Exception:
            return False
        expected = Path(expected_executable_path).resolve(strict=False)
        actual = (Path(application_path) / "acad.exe").resolve(strict=False)
        return version.startswith("25") and actual == expected

    def _user_confirmed_dev_force_matches(self, evidence: RecoveryEvidenceDev) -> bool:
        """OS path 读取不可用时，唯一允许的开发 force 证据组合。"""
        if not evidence.user_confirmed_exact_pid_force or not self._dev_cim_creation_matches(evidence):
            return False
        if self._process_image_name_provider is None:
            return False
        try:
            image_name = self._process_image_name_provider(evidence.process_id)
        except Exception:
            return False
        return str(image_name or "").casefold() == "acad.exe"

    @staticmethod
    def _verified_executable_matches(identity: AutoCadProcessIdentity, expected_path: str) -> bool:
        actual = identity.os_verified_executable_path
        return bool(actual and Path(actual).resolve(strict=False) == Path(expected_path).resolve(strict=False))

    def _call_with_busy_retry(self, operation: Callable[[], Any]) -> Any:
        return read_with_startup_busy_retry(
            operation,
            timeout_seconds=self._policy.timeout_seconds,
            interval_seconds=self._policy.interval_seconds,
            clock=self._clock,
            sleeper=self._sleeper,
        )

    def _wait_until_stopped(self, pid: int) -> bool:
        deadline = self._clock() + self._policy.timeout_seconds
        while self._pid_exists(pid):
            if self._clock() >= deadline:
                return False
            self._sleeper(self._policy.interval_seconds)
        return True

    def _attempt_window_then_force(
        self,
        evidence: RecoveryEvidence,
        environment: Mapping[str, str],
        operations: list[str],
        pid: int,
        hwnd: int | None,
    ) -> RecoveryResult:
        # fallback 前重新校验 PID，防止极端 PID 重用将窗口消息或 force 施加到
        # 同名但不属于此 Job 的新进程。没有 evidence HWND 时不发送窗口消息。
        if not self._still_exact_evidence_process(evidence):
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "FALLBACK_PROCESS_REVERIFY", operations, pid)
        try:
            hwnd_matches = hwnd is not None and hwnd > 0 and self._hwnd_pid_resolver(hwnd) == pid
        except Exception:
            hwnd_matches = False
        if not hwnd_matches:
            return self._result("BLOCKED", "AUTOCAD_COM_INSTANCE_IDENTITY_MISMATCH", "FALLBACK_HWND_PID", operations, pid)
        try:
            normal_close_started = bool(self._normal_window_closer(hwnd))
        except Exception:
            normal_close_started = False
        if not normal_close_started:
            return self._result("FAILED", "AUTOCAD_RECOVERY_NORMAL_CLOSE_FAILED", "NORMAL_WINDOW_CLOSE", operations, pid)
        operations.append("normal_window_close")
        if self._wait_until_stopped(pid):
            return self._result("RECOVERED_WINDOW_CLOSE", None, None, operations, pid)
        if not self._policy.allow_force_termination:
            return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_NOT_AUTHORIZED", "FORCE_GATE", operations, pid)
        if not self._still_exact_evidence_process(evidence):
            return self._result("BLOCKED", "S5_RECOVERY_EVIDENCE_MISMATCH", "FORCE_PROCESS_REVERIFY", operations, pid)
        try:
            force_started = self._force_terminator is not None and bool(self._force_terminator(pid))
        except Exception:
            force_started = False
        if not force_started:
            return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_FAILED", "FORCE_EXACT_PID", operations, pid)
        operations.append("force_exact_pid")
        if self._wait_until_stopped(pid):
            return self._result(
                "RECOVERED_FORCE_EXACT_PID", None, None, operations, pid,
                warnings=("AUTOCAD_JOB_OWNED_PROCESS_FORCE_RECOVERED",),
            )
        return self._result("FAILED", "AUTOCAD_RECOVERY_FORCE_FAILED", "FORCE_EXACT_PID", operations, pid)

    def _still_exact_evidence_process(self, evidence: RecoveryEvidence) -> bool:
        if not self._pid_exists(evidence.process_id):
            return False
        try:
            verified = self._inspect_identity(
                AutoCadProcessIdentity(
                    job_id=evidence.job_id,
                    process_id=evidence.process_id,
                    executable_path=str(Path(evidence.expected_executable_path).resolve(strict=False)),
                    process_start_time=self._clock(),
                    launched_by_job=True,
                    ownership_token=evidence.ownership_token,
                )
            )
        except Exception:
            return False
        return (
            self._verified_executable_matches(verified, evidence.expected_executable_path)
            and verified.os_process_creation_filetime == evidence.process_creation_filetime
        )

    @staticmethod
    def _result(
        status: str,
        error_code: str | None,
        error_stage: str | None,
        operations: list[str],
        pid: int,
        *,
        warnings: tuple[str, ...] = (),
    ) -> RecoveryResult:
        return RecoveryResult(status, error_code, error_stage, tuple(operations), (pid,), warnings)

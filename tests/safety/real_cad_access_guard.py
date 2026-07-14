"""pytest 会话级真实 CAD 文件访问守卫。

本模块只检查路径与命令字符串，不探测、不打开也不哈希 DWG/DXF。
生产代码不依赖本模块；它仅由测试会话加载。
"""

from __future__ import annotations

import builtins
import hashlib
import json
import os
from pathlib import Path, PurePath
import re
import shutil
import subprocess
import sys
import traceback
from typing import Any, Iterable


CAD_EXTENSIONS = {".dwg", ".dxf"}
EXTERNAL_READONLY_MARKERS = {"real_dwg", "external_integration"}
CAD_PROCESS_NAMES = {
    "acad",
    "acad.exe",
    "autocad",
    "autocad.exe",
    "accoreconsole",
    "accoreconsole.exe",
    "tarch",
    "tarch.exe",
}
DANGEROUS_SCRIPT_FRAGMENTS = {
    "preflight",
    "scanner",
    "scan_dwg",
    "dwg_scan",
    "cad_scan",
    "file_sha256",
    "compute_sha256",
    "hash_dwg",
    "run_stage6_p1_accelerated_r4",
}
SCRIPT_INTERPRETERS = {
    "python",
    "python.exe",
    "py",
    "py.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "cmd",
    "cmd.exe",
}


class RealCadAccessViolation(RuntimeError):
    """测试尝试越过真实 CAD 文件或 CAD 进程边界。"""


def _flatten_command(command: Any) -> list[str]:
    if isinstance(command, (str, bytes, os.PathLike)):
        return [os.fsdecode(command)]
    if isinstance(command, Iterable):
        return [os.fsdecode(value) for value in command]
    return [str(command)]


class RealCadAccessGuard:
    """拦截测试会话中的 CAD 文件访问和危险子进程命令。"""

    def __init__(self, project_root: Path, output_dir: Path) -> None:
        self.project_root = project_root.absolute()
        self.output_dir = output_dir.absolute()
        self.log_path = self.output_dir / "default_test_file_access_log.jsonl"
        self.summary_path = self.output_dir / "default_test_file_access_summary.json"
        self._installed = False
        self._current_test = "<collection>"
        self._current_markers: set[str] = set()
        self._synthetic_roots: dict[str, set[str]] = {}
        self._synthetic_files: dict[str, set[str]] = {}
        self._events: list[dict[str, Any]] = []
        self._collected_count = 0
        self._originals: dict[str, Any] = {}
        self._initial_modules = set(sys.modules)

    @classmethod
    def from_environment(cls, project_root: Path) -> "RealCadAccessGuard":
        configured = os.environ.get("CAD_SAFE_TEST_RUN_DIR")
        output_dir = (
            Path(configured)
            if configured
            else project_root / ".pytest_cache" / "cad_safe_test_guard"
        )
        return cls(project_root, output_dir)

    @staticmethod
    def _norm(path: str | os.PathLike[str]) -> str:
        raw = os.path.expandvars(os.path.expanduser(os.fsdecode(path)))
        resolved = Path(raw).resolve(strict=False)
        return os.path.normcase(os.path.normpath(str(resolved)))

    @staticmethod
    def _suffix(path: str | os.PathLike[str]) -> str:
        return PurePath(os.fsdecode(path)).suffix.lower()

    def _is_within(self, path: str, root: str) -> bool:
        try:
            return os.path.commonpath([path, root]) == root
        except ValueError:
            return False

    def _owner(self, owner_test_id: str | None = None) -> str:
        owner = owner_test_id or self._current_test
        if owner in {"<collection>", "<between-tests>", ""}:
            raise ValueError("synthetic 登记必须绑定具体 pytest test_id")
        return owner

    def add_synthetic_root(
        self, root: Path, *, owner_test_id: str | None = None
    ) -> None:
        owner = self._owner(owner_test_id)
        self._synthetic_roots.setdefault(owner, set()).add(self._norm(root))

    def register_synthetic_cad(
        self,
        path: str | os.PathLike[str],
        *,
        synthetic_test_file: bool,
        owner_test_id: str | None = None,
    ) -> None:
        owner = self._owner(owner_test_id)
        if self._suffix(path) not in CAD_EXTENSIONS:
            raise ValueError("仅 CAD 扩展名文件需要 synthetic 登记")
        normalized = self._norm(path)
        if not synthetic_test_file:
            raise ValueError("登记 synthetic CAD 时必须显式声明 synthetic_test_file=true")
        roots = self._synthetic_roots.get(owner, set())
        if not any(self._is_within(normalized, root) for root in roots):
            raise ValueError("synthetic CAD 解析后的真实路径必须仍在 pytest tmp_path 内")
        self._synthetic_files.setdefault(owner, set()).add(normalized)

    def unregister_synthetic_cad(
        self, path: str | os.PathLike[str], *, owner_test_id: str | None = None
    ) -> None:
        owner = self._owner(owner_test_id)
        self._synthetic_files.get(owner, set()).discard(self._norm(path))

    def clear_owner(self, owner_test_id: str) -> None:
        """仅撤销 owner 登记，不删除或修改任何文件。"""

        self._synthetic_files.pop(owner_test_id, None)
        self._synthetic_roots.pop(owner_test_id, None)

    def set_collection(self, items: list[Any]) -> None:
        self._collected_count = len(items)

    def set_test_context(self, item: Any) -> None:
        self._current_test = item.nodeid
        self._current_markers = {marker.name for marker in item.iter_markers()}

    def clear_test_context(self) -> None:
        if self._current_test not in {"<collection>", "<between-tests>", ""}:
            self.clear_owner(self._current_test)
        self._current_test = "<between-tests>"
        self._current_markers = set()

    def _is_sensitive_non_cad_path(self, normalized: str) -> bool:
        roots = (
            self.project_root / "图纸",
            self.project_root / "output",
        )
        return any(self._is_within(normalized, self._norm(root)) for root in roots)

    def evaluate_path(self, path: Any, mode: str) -> tuple[bool, str, str]:
        if isinstance(path, int):
            return True, "file_descriptor", str(path)
        try:
            normalized = self._norm(path)
        except (TypeError, ValueError):
            return True, "non_path_argument", repr(path)

        is_cad = self._suffix(normalized) in CAD_EXTENSIONS
        is_registered = normalized in self._synthetic_files.get(
            self._current_test, set()
        )
        write_requested = any(flag in mode for flag in "wax+")

        if is_registered:
            return True, "registered_synthetic_cad", normalized
        if is_cad or self._is_sensitive_non_cad_path(normalized):
            if (
                not write_requested
                and EXTERNAL_READONLY_MARKERS.issubset(self._current_markers)
                and os.environ.get("CAD_TEST_ALLOW_EXTERNAL_READONLY") == "1"
            ):
                return True, "explicit_external_readonly", normalized
            return False, "real_cad_boundary", normalized
        return True, "non_cad_file", normalized

    def _record(
        self,
        *,
        operation: str,
        path: str,
        mode: str,
        allowed: bool,
        reason: str,
        process: bool = False,
    ) -> None:
        category = "normal"
        if not allowed and "guard_self_test" in self._current_markers:
            category = "expected_guard_self_test_block"
        elif not allowed:
            category = "unexpected_default_test_block"
        event = {
            "test_id": self._current_test,
            "operation": operation,
            "path_or_command": path,
            "mode": mode,
            "allowed": allowed,
            "reason": reason,
            "category": category,
            "markers": sorted(self._current_markers),
            "is_process": process,
            "stack": "".join(traceback.format_stack(limit=12)),
        }
        self._events.append(event)

    def check_path(self, operation: str, path: Any, mode: str = "r") -> tuple[str, str]:
        allowed, reason, normalized = self.evaluate_path(path, mode)
        self._record(
            operation=operation,
            path=normalized,
            mode=mode,
            allowed=allowed,
            reason=reason,
        )
        if not allowed:
            raise RealCadAccessViolation(
                f"SEC-FINAL-019 阻断: test={self._current_test}; "
                f"operation={operation}; mode={mode}; path={normalized}; "
                f"markers={sorted(self._current_markers)}"
            )
        return reason, normalized

    def record_completed_path(
        self, operation: str, normalized: str, mode: str, reason: str
    ) -> None:
        """仅在底层 API 成功返回后记录实际完成的文件访问。"""

        self._record(
            operation=f"{operation}.completed",
            path=normalized,
            mode=mode,
            allowed=True,
            reason=reason,
        )

    def check_command(self, operation: str, command: Any) -> str:
        parts = _flatten_command(command)
        lowered = [part.lower() for part in parts]
        executable = PurePath(parts[0].strip('"')).name.lower() if parts else ""
        reason = "non_cad_subprocess"
        combined = " ".join(lowered)
        token_names = {
            PurePath(token.strip('"\'')).name.lower() for token in parts if token.strip()
        }
        blocked = executable in CAD_PROCESS_NAMES or bool(token_names & CAD_PROCESS_NAMES)
        interpreter = executable in SCRIPT_INTERPRETERS
        if blocked:
            reason = "cad_process_forbidden"
        elif any(
            suffix in token
            for token in lowered
            for suffix in (".dwg", ".dxf")
        ):
            blocked = True
            reason = "cad_path_in_subprocess"
        elif interpreter and any(
            fragment in PurePath(token.strip('"\'')).name.lower()
            for token in parts
            for fragment in DANGEROUS_SCRIPT_FRAGMENTS
        ):
            blocked = True
            reason = "known_cad_access_script_forbidden"
        elif interpreter and re.search(
            r"(?:^|[\\/\s])(acad(?:\.exe)?|accoreconsole(?:\.exe)?)(?:$|\s)",
            combined,
        ):
            blocked = True
            reason = "cad_process_forbidden"

        rendered = subprocess.list2cmdline(parts)
        self._record(
            operation=operation,
            path=rendered,
            mode="execute",
            allowed=not blocked,
            reason=reason,
            process=True,
        )
        if blocked:
            raise RealCadAccessViolation(
                f"SEC-FINAL-019 子进程阻断: test={self._current_test}; "
                f"operation={operation}; command={rendered}; reason={reason}"
            )
        return reason

    def install(self) -> None:
        if self._installed:
            return
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._originals = {
            "builtins.open": builtins.open,
            "builtins.__import__": builtins.__import__,
            "Path.open": Path.open,
            "Path.read_bytes": Path.read_bytes,
            "Path.read_text": Path.read_text,
            "os.open": os.open,
            "shutil.copy": shutil.copy,
            "shutil.copy2": shutil.copy2,
            "shutil.copyfile": shutil.copyfile,
            "subprocess.Popen": subprocess.Popen,
        }
        guard = self

        def guarded_open(file, mode="r", *args, **kwargs):
            reason, normalized = guard.check_path("builtins.open", file, str(mode))
            result = guard._originals["builtins.open"](file, mode, *args, **kwargs)
            guard.record_completed_path("builtins.open", normalized, str(mode), reason)
            return result

        def guarded_path_open(path_self, mode="r", *args, **kwargs):
            reason, normalized = guard.check_path("Path.open", path_self, str(mode))
            result = guard._originals["Path.open"](path_self, mode, *args, **kwargs)
            guard.record_completed_path("Path.open", normalized, str(mode), reason)
            return result

        def guarded_read_bytes(path_self):
            reason, normalized = guard.check_path("Path.read_bytes", path_self, "rb")
            result = guard._originals["Path.read_bytes"](path_self)
            guard.record_completed_path("Path.read_bytes", normalized, "rb", reason)
            return result

        def guarded_read_text(path_self, *args, **kwargs):
            reason, normalized = guard.check_path("Path.read_text", path_self, "r")
            result = guard._originals["Path.read_text"](path_self, *args, **kwargs)
            guard.record_completed_path("Path.read_text", normalized, "r", reason)
            return result

        def guarded_os_open(path, flags, *args, **kwargs):
            write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            mode = "wb" if flags & write_flags else "rb"
            reason, normalized = guard.check_path("os.open", path, mode)
            result = guard._originals["os.open"](path, flags, *args, **kwargs)
            guard.record_completed_path("os.open", normalized, mode, reason)
            return result

        def make_copy_wrapper(name):
            def wrapper(src, dst, *args, **kwargs):
                src_reason, src_normalized = guard.check_path(
                    f"shutil.{name}:src", src, "rb"
                )
                dst_reason, dst_normalized = guard.check_path(
                    f"shutil.{name}:dst", dst, "wb"
                )
                result = guard._originals[f"shutil.{name}"](
                    src, dst, *args, **kwargs
                )
                guard.record_completed_path(
                    f"shutil.{name}:src", src_normalized, "rb", src_reason
                )
                guard.record_completed_path(
                    f"shutil.{name}:dst", dst_normalized, "wb", dst_reason
                )
                return result

            return wrapper

        def guarded_popen(args, *popen_args, **popen_kwargs):
            reason = guard.check_command("subprocess.Popen", args)
            result = guard._originals["subprocess.Popen"](
                args, *popen_args, **popen_kwargs
            )
            guard._record(
                operation="subprocess.started",
                path=subprocess.list2cmdline(_flatten_command(args)),
                mode="execute",
                allowed=True,
                reason=reason,
                process=True,
            )
            return result

        def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
            root_name = str(name).split(".", 1)[0].lower()
            if root_name in {"win32com", "pythoncom", "comtypes"}:
                mock_module = sys.modules.get(str(name)) or sys.modules.get(root_name)
                if getattr(mock_module, "__cad_test_mock__", False) is True:
                    return guard._originals["builtins.__import__"](
                        name, globals, locals, fromlist, level
                    )
                guard._record(
                    operation="builtins.__import__",
                    path=str(name),
                    mode="import",
                    allowed=False,
                    reason="com_import_forbidden",
                )
                raise RealCadAccessViolation(
                    f"SEC-FINAL-019 COM 导入阻断: test={guard._current_test}; module={name}"
                )
            return guard._originals["builtins.__import__"](
                name, globals, locals, fromlist, level
            )

        builtins.open = guarded_open
        builtins.__import__ = guarded_import
        Path.open = guarded_path_open
        Path.read_bytes = guarded_read_bytes
        Path.read_text = guarded_read_text
        os.open = guarded_os_open
        shutil.copy = make_copy_wrapper("copy")
        shutil.copy2 = make_copy_wrapper("copy2")
        shutil.copyfile = make_copy_wrapper("copyfile")
        subprocess.Popen = guarded_popen
        self._installed = True

    def uninstall(self) -> None:
        if not self._installed:
            return
        builtins.open = self._originals["builtins.open"]
        builtins.__import__ = self._originals["builtins.__import__"]
        Path.open = self._originals["Path.open"]
        Path.read_bytes = self._originals["Path.read_bytes"]
        Path.read_text = self._originals["Path.read_text"]
        os.open = self._originals["os.open"]
        shutil.copy = self._originals["shutil.copy"]
        shutil.copy2 = self._originals["shutil.copy2"]
        shutil.copyfile = self._originals["shutil.copyfile"]
        subprocess.Popen = self._originals["subprocess.Popen"]
        self._installed = False

    def build_summary(self) -> dict[str, Any]:
        expected_blocks = [
            event
            for event in self._events
            if event["category"] == "expected_guard_self_test_block"
        ]
        unexpected_blocks = [
            event
            for event in self._events
            if event["category"] == "unexpected_default_test_block"
            and not event["is_process"]
            and event["reason"] == "real_cad_boundary"
        ]
        synthetic = [
            event
            for event in self._events
            if event["reason"] == "registered_synthetic_cad" and event["allowed"]
            and event["operation"].endswith(".completed")
        ]
        subprocess_audits = [
            event
            for event in self._events
            if event["is_process"] and event["operation"] == "subprocess.Popen"
        ]
        started_processes = [
            event
            for event in self._events
            if event["is_process"] and event["operation"] == "subprocess.started"
        ]
        completed_real_reads = [
            event
            for event in self._events
            if event["operation"].endswith(".completed")
            and event["reason"] == "explicit_external_readonly"
            and not any(flag in event["mode"] for flag in "wax+")
        ]
        completed_real_writes = [
            event
            for event in self._events
            if event["operation"].endswith(".completed")
            and event["reason"] == "explicit_external_readonly"
            and any(flag in event["mode"] for flag in "wax+")
        ]
        com_connection_events = [
            event
            for event in self._events
            if event["operation"] == "autocad_com_connection.completed"
        ]
        tianzheng_connection_events = [
            event
            for event in self._events
            if event["operation"] == "tianzheng_connection.completed"
        ]
        newly_imported_com_modules = sorted(
            name
            for name in set(sys.modules) - self._initial_modules
            if name.split(".", 1)[0].lower() in {"win32com", "pythoncom", "comtypes"}
        )
        return {
            "schema_version": "1.0.0",
            "guard_enabled": True,
            "collected_count": self._collected_count,
            "total_file_access_events": sum(
                not event["is_process"] for event in self._events
            ),
            "cad_extension_access_attempts": sum(
                any(ext in event["path_or_command"].lower() for ext in CAD_EXTENSIONS)
                for event in self._events
                if not event["is_process"]
            ),
            "real_dwg_access_attempts": len(unexpected_blocks),
            "blocked_real_dwg_attempts": len(unexpected_blocks),
            "expected_guard_self_test_blocked_attempts": len(expected_blocks),
            "allowed_synthetic_cad_accesses": len(synthetic),
            "real_dwg_successful_reads": len(completed_real_reads),
            "real_dwg_successful_writes": len(completed_real_writes),
            "external_processes_started": len(started_processes),
            "blocked_subprocess_attempts": sum(
                not event["allowed"] for event in subprocess_audits
            ),
            "cad_processes_started": sum(
                event["reason"] == "cad_process_started" for event in started_processes
            ),
            "autocad_com_connections": len(com_connection_events),
            "tianzheng_connections": len(tianzheng_connection_events),
            "newly_imported_com_modules": newly_imported_com_modules,
        }

    def finalize(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        with self._originals.get("builtins.open", builtins.open)(
            self.log_path, "w", encoding="utf-8", newline="\n"
        ) as stream:
            for event in self._events:
                stream.write(json.dumps(event, ensure_ascii=False) + "\n")
        with self._originals.get("builtins.open", builtins.open)(
            self.summary_path, "w", encoding="utf-8", newline="\n"
        ) as stream:
            json.dump(self.build_summary(), stream, ensure_ascii=False, indent=2)
            stream.write("\n")


def guarded_file_sha256(path: str | os.PathLike[str], guard: RealCadAccessGuard) -> str:
    """供测试辅助代码复用的受守卫哈希入口。"""

    reason, normalized = guard.check_path("guarded_file_sha256", path, "rb")
    digest = hashlib.sha256()
    with guard._originals.get("builtins.open", builtins.open)(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    guard.record_completed_path("guarded_file_sha256", normalized, "rb", reason)
    return digest.hexdigest()

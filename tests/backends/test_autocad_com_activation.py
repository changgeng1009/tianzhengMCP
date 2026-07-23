"""S5 COM activation 与运行时环境合同的纯 Mock 测试。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from mcp_nextgen.backends.autocad_com_activation import (
    ComActivationSessionHost,
    EnvironmentValueState,
    IsolatedComActivator,
    RealComLaunchPolicy,
    REQUIRED_ENVIRONMENT_KEYS,
    RPC_E_CALL_REJECTED,
    RPC_E_SERVERCALL_RETRYLATER,
    WindowsEnvironmentRecovery,
    normalize_child_environment,
    read_with_startup_busy_retry,
    sanitize_child_environment,
    validate_external_runtime_cwd,
)
from mcp_nextgen.backends.autocad_launcher import AutoCadLauncherError


VALID_ENV = {
    "SystemDrive": "C:",
    "SystemRoot": r"C:\Windows",
    "windir": r"%SystemRoot%",
    "ProgramData": "%SystemDrive%\\ProgramData",
    "ALLUSERSPROFILE": "%ProgramData%",
    "USERPROFILE": r"C:\Users\REDACTED_USER",
    "APPDATA": r"%USERPROFILE%\AppData\Roaming",
    "LOCALAPPDATA": r"%USERPROFILE%\AppData\Local",
    "TEMP": r"%LOCALAPPDATA%\Temp",
    "TMP": r"%LOCALAPPDATA%\Temp",
}


RECOVERY_VALUES = {
    "windows": r"C:\Windows",
    "ProgramData": r"C:\ProgramData",
    "Profile": r"C:\Users\REDACTED_USER",
    "RoamingAppData": r"C:\Users\REDACTED_USER\AppData\Roaming",
    "LocalAppData": r"C:\Users\REDACTED_USER\AppData\Local",
}


def trusted_recovery(*, unavailable: set[str] | None = None) -> WindowsEnvironmentRecovery:
    """纯注入的 Windows API 返回值；不查询宿主、不读取用户配置。"""
    unavailable = unavailable or set()
    return WindowsEnvironmentRecovery(
        windows_directory=lambda: None if "windows" in unavailable else RECOVERY_VALUES["windows"],
        known_folder=lambda name: None if name in unavailable else RECOVERY_VALUES.get(name),
    )


def expected_recovered_value(key: str) -> str:
    values = {
        "SystemDrive": "C:", "SystemRoot": RECOVERY_VALUES["windows"], "windir": RECOVERY_VALUES["windows"],
        "ProgramData": RECOVERY_VALUES["ProgramData"], "ALLUSERSPROFILE": RECOVERY_VALUES["ProgramData"],
        "USERPROFILE": RECOVERY_VALUES["Profile"], "APPDATA": RECOVERY_VALUES["RoamingAppData"],
        "LOCALAPPDATA": RECOVERY_VALUES["LocalAppData"],
        "TEMP": RECOVERY_VALUES["LocalAppData"] + r"\Temp", "TMP": RECOVERY_VALUES["LocalAppData"] + r"\Temp",
    }
    return values[key]


class FakeClient:
    def __init__(self) -> None:
        self.dispatch_ex_calls: list[str] = []
        self.dispatch_calls: list[str] = []

    def DispatchEx(self, progid: str):
        self.dispatch_ex_calls.append(progid)
        return {"progid": progid}

    def Dispatch(self, progid: str):
        self.dispatch_calls.append(progid)
        raise AssertionError("普通 Dispatch 不得被调用")


class FakeComBusyError(RuntimeError):
    def __init__(self, hresult: int) -> None:
        super().__init__(hresult, "synthetic COM startup busy")
        self.hresult = hresult


def test_real_com_default_mode_is_com_activation() -> None:
    assert RealComLaunchPolicy().mode == "com_activation"


def test_environment_expands_and_normalizes_only_required_values() -> None:
    result = normalize_child_environment(VALID_ENV)
    assert result == {
        "SystemDrive": "C:", "SystemRoot": r"C:\Windows", "windir": r"C:\Windows",
        "ProgramData": r"C:\ProgramData", "ALLUSERSPROFILE": r"C:\ProgramData",
        "USERPROFILE": r"C:\Users\REDACTED_USER", "APPDATA": r"C:\Users\REDACTED_USER\AppData\Roaming",
        "LOCALAPPDATA": r"C:\Users\REDACTED_USER\AppData\Local",
        "TEMP": r"C:\Users\REDACTED_USER\AppData\Local\Temp", "TMP": r"C:\Users\REDACTED_USER\AppData\Local\Temp",
    }


def test_environment_masks_noncritical_unresolved_tokens_without_revealing_values() -> None:
    result = sanitize_child_environment({**VALID_ENV, "NONCRITICAL": "%UNKNOWN_SECRET%"})
    assert result.warnings == ({"name": "NONCRITICAL", "unresolved_tokens": ["%UNKNOWN_SECRET%"]},)
    assert "%UNKNOWN_SECRET%" not in str(result.environment)


def test_missing_systemdrive_is_derived_only_from_valid_systemroot_and_is_warned() -> None:
    environment = dict(VALID_ENV)
    environment.pop("SystemDrive")
    result = sanitize_child_environment(environment)
    assert result.environment["SystemDrive"] == "C:"
    assert {"name": "SystemDrive", "derived": "SystemRoot"} in result.warnings
    unsafe = dict(environment, SystemRoot=r"T:\Windows")
    with pytest.raises(AutoCadLauncherError) as error:
        sanitize_child_environment(unsafe)
    assert error.value.error_code == "AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID"


def test_windir_only_safely_supplies_systemroot_and_systemdrive() -> None:
    environment = dict(VALID_ENV)
    environment.pop("SystemDrive")
    environment.pop("SystemRoot")
    environment["windir"] = r"C:\Windows"
    result = sanitize_child_environment(environment)
    assert result.environment["SystemDrive"] == "C:"
    assert result.environment["SystemRoot"] == r"C:\Windows"
    assert {"name": "SystemRoot", "derived": "windir"} in result.warnings
    assert {"name": "SystemDrive", "derived": "windir"} in result.warnings


@pytest.mark.parametrize("missing_key", REQUIRED_ENVIRONMENT_KEYS)
def test_each_missing_critical_environment_value_is_recovered_from_injected_trusted_source(missing_key: str) -> None:
    source = dict(VALID_ENV)
    source.pop(missing_key)
    source_before = dict(source)
    result = sanitize_child_environment(source, recovery=trusted_recovery())
    assert source == source_before
    assert result.environment[missing_key] == expected_recovered_value(missing_key)
    assert result.states[missing_key] == EnvironmentValueState.RECOVERABLE.value
    assert any(item["name"] == missing_key and item.get("state") == "Recoverable" for item in result.warnings) or missing_key == "SystemDrive"


@pytest.mark.parametrize("unresolved_key", REQUIRED_ENVIRONMENT_KEYS)
def test_each_unresolved_critical_environment_value_is_replaced_from_trusted_source_without_value_leak(unresolved_key: str) -> None:
    secret = "%S5_UNRESOLVED_SECRET_VALUE%"
    source = dict(VALID_ENV)
    source[unresolved_key] = secret
    result = sanitize_child_environment(source, recovery=trusted_recovery())
    assert result.environment[unresolved_key] == expected_recovered_value(unresolved_key)
    assert result.states[unresolved_key] == EnvironmentValueState.RECOVERABLE.value
    assert secret not in str(result.warnings)
    assert secret not in str(result.states)


def test_only_unresolvable_trusted_recovery_blocks_and_does_not_echo_sensitive_value() -> None:
    source = dict(VALID_ENV)
    source["USERPROFILE"] = "%S5_TOP_SECRET%"
    with pytest.raises(AutoCadLauncherError) as error:
        sanitize_child_environment(source, recovery=trusted_recovery(unavailable={"Profile"}))
    assert error.value.error_code == "AUTOCAD_LAUNCH_ENVIRONMENT_UNRESOLVABLE"
    assert "S5_TOP_SECRET" not in str(error.value)


@pytest.mark.parametrize(
    ("environment", "error_code"),
    [
        ({"SystemDrive": "C:", "ProgramData": "relative", "ALLUSERSPROFILE": "C:\\ProgramData"}, "AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID"),
        ({"SystemDrive": "T:", "ProgramData": "T:\\ProgramData", "ALLUSERSPROFILE": "T:\\ProgramData"}, "AUTOCAD_LAUNCH_ENVIRONMENT_PATH_INVALID"),
    ],
)
def test_environment_rejects_untrusted_or_unexpanded_paths(environment, error_code: str) -> None:
    environment = {**VALID_ENV, **environment}
    with pytest.raises(AutoCadLauncherError) as error:
        normalize_child_environment(environment)
    assert error.value.error_code == error_code


def test_external_runtime_cwd_is_fixed_and_non_project() -> None:
    assert "cadagentruntime" in str(validate_external_runtime_cwd(r"D:\CadAgentRuntime\s5\launch")).lower()
    with pytest.raises(AutoCadLauncherError) as error:
        validate_external_runtime_cwd(r"D:\CodexWork\天正")
    assert error.value.error_code == "AUTOCAD_LAUNCH_WORKING_DIRECTORY_UNSAFE"


def test_isolated_activator_uses_dispatchex_not_dispatch() -> None:
    client = FakeClient()
    result = IsolatedComActivator(client_importer=lambda: client).activate("AutoCAD.Application.25.1")
    assert result == {"progid": "AutoCAD.Application.25.1"}
    assert client.dispatch_ex_calls == ["AutoCAD.Application.25.1"]
    assert client.dispatch_calls == []


def test_startup_busy_retry_retries_two_call_rejected_then_succeeds_without_reactivation() -> None:
    attempts = 0
    sleeps: list[float] = []

    def read_only_operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts <= 2:
            raise FakeComBusyError(RPC_E_CALL_REJECTED)
        return "25.1"

    assert read_with_startup_busy_retry(
        read_only_operation, clock=lambda: 0.0, sleeper=sleeps.append,
    ) == "25.1"
    assert attempts == 3
    assert sleeps == [0.5, 0.5]


def test_startup_busy_retry_retries_retrylater_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    def read_only_operation() -> int:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise FakeComBusyError(RPC_E_SERVERCALL_RETRYLATER)
        return 4242

    assert read_with_startup_busy_retry(
        read_only_operation, clock=lambda: 0.0, sleeper=sleeps.append,
    ) == 4242
    assert attempts == 2
    assert sleeps == [0.5]


def test_startup_busy_retry_does_not_retry_non_retryable_error() -> None:
    calls = 0
    sleeps: list[float] = []

    def read_only_operation() -> None:
        nonlocal calls
        calls += 1
        raise FakeComBusyError(0x80004005)

    with pytest.raises(FakeComBusyError):
        read_with_startup_busy_retry(read_only_operation, clock=lambda: 0.0, sleeper=sleeps.append)
    assert calls == 1
    assert sleeps == []


def test_startup_busy_retry_times_out_without_second_activation_or_process() -> None:
    calls = 0
    sleeps: list[float] = []
    ticks = iter((0.0, 1.0, 45.0))

    def read_only_operation() -> None:
        nonlocal calls
        calls += 1
        raise FakeComBusyError(RPC_E_CALL_REJECTED)

    with pytest.raises(AutoCadLauncherError) as error:
        read_with_startup_busy_retry(read_only_operation, clock=lambda: next(ticks), sleeper=sleeps.append)
    assert error.value.error_code == "AUTOCAD_COM_STARTUP_BUSY_TIMEOUT"
    assert calls == 2
    assert sleeps == [0.5]


def test_runner_retries_only_post_activation_read_operations_and_never_starts_second_process() -> None:
    source = (Path(__file__).parents[2] / "mcp_nextgen" / "backends" / "s5_synthetic_runner.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    activation_calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "activate"
    ]
    retry_lambdas = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "read_with_startup_busy_retry"
    ]
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    assert len(activation_calls) == 1
    assert len(retry_lambdas) >= 4
    assert "Popen" not in names and "DispatchEx" not in names and "GetActiveObject" not in names


def test_session_host_rejects_process_launch_for_real_com_without_entering_context() -> None:
    with pytest.raises(AutoCadLauncherError) as error:
        ComActivationSessionHost(policy=RealComLaunchPolicy(mode="process_launch"), environment=VALID_ENV)
    assert error.value.error_code == "AUTOCAD_COM_ACTIVATION_REQUIRED"

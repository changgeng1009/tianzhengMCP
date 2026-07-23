"""NextGen 隔离 backend。"""

from .base import BackendError, BackendUnavailableError, ICadBackend
from .autocad_com_activation import (
    ComActivationSessionHost,
    EnvironmentSanitization,
    EnvironmentValueState,
    IsolatedComActivator,
    RealComLaunchPolicy,
    normalize_child_environment,
    read_with_startup_busy_retry,
    sanitize_child_environment,
    validate_external_runtime_cwd,
    WindowsEnvironmentRecovery,
)
from .autocad_launcher import (
    AutoCadExecutableResolver,
    AutoCadLaunchPolicy,
    AutoCadLauncherError,
    AutoCadProcessIdentity,
    AutoCadProcessLauncher,
    AutoCadProcessOwnershipRegistry,
    AutoCadJobOwnedSessionGuard,
    AutoCadDocumentSnapshot,
    AutoCadSessionIdentity,
    AutoCadSessionVerification,
    LazyAutoCadComTransport,
    SafeAutoCadPopen,
    SafeShutdownPlan,
    WindowsAcadProcessInspector,
    WindowsHwndPidResolver,
    WindowsProcessIdentityInspector,
)
from .mock import MockCadBackend
from .autocad_com_gateway import (
    AutoCadComGatewayError, ComSafeArrayAdapter, LazyPywin32SafeArrayAdapter, PureValueSafeArrayAdapter,
    Pywin32AutoCadSandboxGateway,
)
from .s5_synthetic_runner import run_s5_synthetic_mvp
from .s5_autocad_recovery import (
    DEVELOPMENT_RECOVERY_ENV,
    RecoveryEvidence,
    RecoveryEvidenceDev,
    RecoveryPolicy,
    RecoveryResult,
    S5AutoCadRecovery,
    WindowsExactPidTopLevelWindowResolver,
)
from .models import BackendCapability, BackendSession, FailureInjection, MockEntity, ProtectedRegion
from .real_autocad_com import (
    AutoCadComSandboxGateway,
    CircleSpec,
    DocumentOwnershipRegistry,
    EntityRecord,
    L3SyntheticSandboxApproval,
    LineSpec,
    Point3,
    PolylineSpec,
    RealAutoCadComBackend,
    RealAutoCadComBackendError,
    SyntheticAutoCadDocumentIdentity,
)

__all__ = [
    "BackendCapability", "BackendError", "BackendSession", "BackendUnavailableError",
    "ComActivationSessionHost", "EnvironmentSanitization", "EnvironmentValueState", "IsolatedComActivator", "RealComLaunchPolicy",
    "normalize_child_environment", "read_with_startup_busy_retry", "sanitize_child_environment", "validate_external_runtime_cwd", "WindowsEnvironmentRecovery",
    "AutoCadExecutableResolver", "AutoCadLaunchPolicy", "AutoCadLauncherError",
    "AutoCadProcessIdentity", "AutoCadProcessLauncher", "AutoCadProcessOwnershipRegistry",
    "AutoCadJobOwnedSessionGuard", "AutoCadDocumentSnapshot", "AutoCadSessionIdentity",
    "AutoCadSessionVerification", "LazyAutoCadComTransport", "SafeAutoCadPopen",
    "SafeShutdownPlan", "WindowsAcadProcessInspector", "WindowsHwndPidResolver",
    "WindowsProcessIdentityInspector",
    "AutoCadComSandboxGateway", "CircleSpec", "DocumentOwnershipRegistry", "EntityRecord",
    "AutoCadComGatewayError", "ComSafeArrayAdapter", "LazyPywin32SafeArrayAdapter", "PureValueSafeArrayAdapter", "Pywin32AutoCadSandboxGateway",
    "run_s5_synthetic_mvp",
    "DEVELOPMENT_RECOVERY_ENV", "RecoveryEvidence", "RecoveryEvidenceDev",
    "RecoveryPolicy", "RecoveryResult", "S5AutoCadRecovery",
    "WindowsExactPidTopLevelWindowResolver",
    "L3SyntheticSandboxApproval", "LineSpec", "Point3", "PolylineSpec",
    "RealAutoCadComBackend", "RealAutoCadComBackendError", "SyntheticAutoCadDocumentIdentity",
    "FailureInjection", "ICadBackend", "MockCadBackend", "MockEntity", "ProtectedRegion",
]

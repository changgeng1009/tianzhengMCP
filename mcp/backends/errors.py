from __future__ import annotations


class BackendError(RuntimeError):
    """所有 backend 异常的统一基类。"""

    def __init__(self, code: str, message: str, *, backend_id: str = "", details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.backend_id = backend_id
        self.details = dict(details or {})

    def to_dict(self) -> dict:
        return {
            "error_code": self.code,
            "error_message": self.message,
            "backend_id": self.backend_id,
            "details": self.details,
        }


class BackendUnavailableError(BackendError):
    def __init__(self, backend_id: str, message: str = "backend is unavailable") -> None:
        super().__init__("backend_unavailable", message, backend_id=backend_id)


class BackendCapabilityError(BackendError):
    def __init__(self, backend_id: str, missing: list[str]) -> None:
        super().__init__(
            "missing_capability",
            "backend lacks required capabilities: " + ", ".join(missing),
            backend_id=backend_id,
            details={"missing_capabilities": missing},
        )


class BackendSafetyError(BackendError):
    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__("safety_gate_rejected", message, backend_id="router", details=details)

class SkillRuntimeError(RuntimeError):
    code = "SKILL_RUNTIME_ERROR"

    def __init__(self, message: str):
        super().__init__(message)


class RuntimeModeConflict(SkillRuntimeError):
    code = "RUNTIME_MODE_CONFLICT"


class ProductInstanceConflict(SkillRuntimeError):
    code = "PRODUCT_INSTANCE_CONFLICT"


class DocumentIdentityAmbiguous(SkillRuntimeError):
    code = "DOCUMENT_IDENTITY_AMBIGUOUS"


class UnsafeOperation(SkillRuntimeError):
    code = "UNSAFE_OPERATION"


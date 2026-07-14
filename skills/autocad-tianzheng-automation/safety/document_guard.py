from collections.abc import Mapping

from runtime.errors import DocumentIdentityAmbiguous, UnsafeOperation


def verify_document_identity(expected: Mapping[str, object], observed: Mapping[str, object]) -> None:
    required = ("document_identity", "document_sha256")
    if any(not expected.get(key) or not observed.get(key) for key in required):
        raise DocumentIdentityAmbiguous("文档身份或哈希缺失")
    if any(expected[key] != observed[key] for key in required):
        raise DocumentIdentityAmbiguous("ActiveDocument 与批准身份不一致")
    if observed.get("is_source") is True and observed.get("write_requested") is True:
        raise UnsafeOperation("禁止写入源 DWG")

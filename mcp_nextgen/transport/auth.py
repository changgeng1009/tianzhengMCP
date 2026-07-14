"""注入式本地令牌校验；源码中不保存固定令牌。"""

from __future__ import annotations

import hashlib
import hmac


class TokenAuthenticator:
    """只保存 SHA-256 摘要，并使用 constant-time 比较。"""

    def __init__(self, token_sha256: str):
        if len(token_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in token_sha256):
            raise ValueError("token_sha256 必须是 64 位小写十六进制摘要")
        self._token_sha256 = token_sha256

    @classmethod
    def from_token(cls, token: str) -> "TokenAuthenticator":
        if not isinstance(token, str) or len(token) < 32:
            raise ValueError("本地鉴权令牌必须由外部注入且至少 32 个字符")
        return cls(hashlib.sha256(token.encode("utf-8")).hexdigest())

    def verify(self, candidate: str) -> bool:
        if not isinstance(candidate, str) or not candidate:
            return False
        candidate_hash = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
        return hmac.compare_digest(candidate_hash, self._token_sha256)

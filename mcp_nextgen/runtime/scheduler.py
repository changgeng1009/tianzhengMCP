"""确定性主线程调度模拟；不创建真实 AutoCAD 线程。"""

from __future__ import annotations

from collections.abc import Callable
import threading
from typing import Any, TypeVar


T = TypeVar("T")


class MainThreadViolation(RuntimeError):
    pass


class MockMainThreadScheduler:
    """绑定初始化线程并串行执行；跨线程调用被明确拒绝。"""

    def __init__(self) -> None:
        self.owner_thread_id = threading.get_ident()
        self.invocation_count = 0
        self._lock = threading.RLock()

    def invoke(self, callback: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        if threading.get_ident() != self.owner_thread_id:
            raise MainThreadViolation("Mock DocumentContext 操作必须在 runtime 主线程调度")
        with self._lock:
            self.invocation_count += 1
            return callback(*args, **kwargs)

"""取消和超时只在安全边界生效，不能打断 journal/checkpoint 临界区。"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import time


class CancellationRequested(RuntimeError):
    pass


class DeadlineExceeded(TimeoutError):
    pass


@dataclass
class SafeBoundaryController:
    deadline_monotonic: float | None = None
    cancellation_requested: bool = False
    _critical_depth: int = 0

    @classmethod
    def with_timeout(cls, timeout_seconds: float | None) -> "SafeBoundaryController":
        deadline = None if timeout_seconds is None else time.monotonic() + max(0.0, timeout_seconds)
        return cls(deadline_monotonic=deadline)

    def request_cancellation(self) -> None:
        self.cancellation_requested = True

    def check(self) -> None:
        if self._critical_depth:
            return
        if self.cancellation_requested:
            raise CancellationRequested("取消将在安全边界生效")
        if self.deadline_monotonic is not None and time.monotonic() >= self.deadline_monotonic:
            raise DeadlineExceeded("作业已超过截止时间")

    @contextmanager
    def persistence_critical_section(self):
        self._critical_depth += 1
        try:
            yield
        finally:
            self._critical_depth -= 1


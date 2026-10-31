# -*- coding: utf-8 -*-
"""任务取消、进度汇报与统一异常。"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable


class TaskCancelled(RuntimeError):
    pass


class DependencyMissingError(RuntimeError):
    pass


class MediaConversionError(RuntimeError):
    pass


@dataclass
class BatchResult:
    success: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False


class Reporter:
    """把后台进度/状态发送到任意 sink，GUI 用队列，CLI 用 print。"""

    def __init__(self, sink: Callable[[dict[str, Any]], None] | Any = None) -> None:
        self._sink = sink

    def _send(self, payload: dict[str, Any]) -> None:
        if self._sink is None:
            return
        if isinstance(self._sink, Callable):
            self._sink(payload)
            return
        put = getattr(self._sink, "put", None)
        if put is not None:
            try:
                put(payload, timeout=20)
            except Exception:
                pass

    def status(self, text: str) -> None:
        self._send({"kind": "status", "text": text})

    def progress(self, value: float, label: str = "") -> None:
        payload = {"kind": "progress", "value": max(0.0, min(100.0, float(value)))}
        if label:
            payload["label"] = label
        self._send(payload)

    def message(self, kind: str, level: str, text: str) -> None:
        self._send(
            {
                "kind": kind,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "level": level,
                "message": text,
            }
        )

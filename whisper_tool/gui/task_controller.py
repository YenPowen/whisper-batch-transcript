# -*- coding: utf-8 -*-
"""后台任务控制器：multiprocessing 进程 + 队列 + 可强制取消。"""

from __future__ import annotations

import logging
import multiprocessing as mp
import queue
import time
from dataclasses import dataclass
from typing import Callable

from ..core.runner import worker_entry
from ..core.task_params import TaskParams


LOGGER = logging.getLogger(__name__)


@dataclass
class TaskOutcome:
    ok: bool
    message: str
    success: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False
    output: str = ""


class TaskController:
    def __init__(
        self,
        root,
        on_log: Callable[[str, str], None],
        on_progress: Callable[[float], None],
        on_status: Callable[[str], None],
        on_finished: Callable[[TaskOutcome], None],
    ) -> None:
        self._root = root
        self._on_log = on_log
        self._on_progress = on_progress
        self._on_status = on_status
        self._on_finished = on_finished
        self._process: mp.Process | None = None
        self._queue: mp.Queue | None = None
        self._cancel_event: mp.Event | None = None
        self._done_payload: dict | None = None
        self._force_deadline = 0.0

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.is_alive()

    def start(self, params: TaskParams) -> None:
        if self.running:
            raise RuntimeError("已有任务在运行")
        self._queue = mp.Queue(maxsize=2000)
        self._cancel_event = mp.Event()
        self._done_payload = None
        self._process = mp.Process(
            target=worker_entry,
            args=(params, self._cancel_event, self._queue),
            name="whisper-task-worker",
            daemon=True,
        )
        self._process.start()
        self._root.after(80, self._poll_queue)

    def cancel(self, hard_after_seconds: float = 2.0) -> None:
        if not self.running:
            return
        if self._cancel_event is not None:
            self._cancel_event.set()
        self._force_deadline = time.monotonic() + hard_after_seconds
        self._on_log("WARN", "已请求停止；2 秒后仍未退出将强制结束任务进程")
        self._schedule_force_kill()

    def _schedule_force_kill(self) -> None:
        if not self.running:
            return
        now = time.monotonic()
        if now >= self._force_deadline:
            if self._process is not None and self._process.is_alive():
                self._on_log("WARN", "任务未在限定时间内响应，强制终止后台进程")
                try:
                    self._process.terminate()
                except Exception as exc:
                    LOGGER.warning("强制结束进程失败: %s", exc)
            return
        self._root.after(250, self._schedule_force_kill)

    def shutdown(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
        process = self._process
        if process is not None and process.is_alive():
            process.terminate()
            process.join(timeout=3)

    def _poll_queue(self) -> None:
        if self._process is None or self._queue is None:
            return
        while True:
            try:
                payload = self._queue.get_nowait()
            except queue.Empty:
                break
            self._handle_payload(payload)

        if self._process.is_alive():
            self._root.after(80, self._poll_queue)
            return

        try:
            while True:
                payload = self._queue.get(timeout=0.05)
                self._handle_payload(payload)
        except queue.Empty:
            pass
        except Exception as exc:
            LOGGER.warning("读取任务队列时出错: %s", exc)

        self._process.join(timeout=0.5)
        payload = self._done_payload or {
            "ok": False,
            "message": "任务进程意外退出，未返回完成事件",
            "cancelled": bool(self._cancel_event and self._cancel_event.is_set()),
        }
        self._finish(payload)

    def _handle_payload(self, payload: dict) -> None:
        kind = payload.get("kind")
        if kind == "log":
            self._on_log(str(payload.get("level", "INFO")), str(payload.get("message", "")))
        elif kind == "progress":
            self._on_progress(float(payload.get("value", 0)))
        elif kind == "status":
            self._on_status(str(payload.get("text", "")))
        elif kind == "done":
            self._done_payload = payload
        elif kind == "error":
            self._on_log("ERROR", str(payload.get("message", "未知错误")))

    def _finish(self, payload: dict) -> None:
        process = self._process
        if process is not None:
            try:
                process.join(timeout=1)
            except Exception:
                pass
        outcome = TaskOutcome(
            ok=bool(payload.get("ok")),
            message=str(payload.get("message", "")),
            success=int(payload.get("success", 0)),
            failed=int(payload.get("failed", 0)),
            skipped=int(payload.get("skipped", 0)),
            cancelled=bool(payload.get("cancelled", False)),
            output=str(payload.get("output", "")),
        )
        self._process = None
        self._queue = None
        self._cancel_event = None
        self._on_finished(outcome)

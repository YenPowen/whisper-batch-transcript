# -*- coding: utf-8 -*-
"""标准 logging 配置：文件、控制台与后台进程事件队列。"""

from __future__ import annotations

import logging
import logging.handlers
import time
from pathlib import Path
from typing import Any, Callable


SUCCESS = 25
logging.addLevelName(SUCCESS, "SUCCESS")


def log_success(logger: logging.Logger, message: str) -> None:
    logger.log(SUCCESS, message)


def setup_base_logging(
    log_path: Path | None = None,
    console_handler: logging.Handler | None = None,
) -> logging.Handler | None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = None
    if log_path is not None:
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_path),
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    if console_handler is None:
        stream = logging.StreamHandler()
        stream.setFormatter(formatter)
        root.addHandler(stream)
        console_handler = stream
    else:
        console_handler.setFormatter(formatter)
        root.addHandler(console_handler)
    return file_handler


class QueueLogHandler(logging.Handler):
    """将后台进程的日志序列化后放入事件队列。"""

    def __init__(self, queue: Any) -> None:
        super().__init__(level=logging.INFO)
        self._queue = queue

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            payload = {
                "kind": "log",
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "level": record.levelname,
                "message": message,
            }
            self._queue.put(payload, timeout=20)
        except Exception:
            self.handleError(record)


def install_queue_logging(queue: Any) -> Callable[[], None]:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    handler = QueueLogHandler(queue)
    root.addHandler(handler)

    def uninstall() -> None:
        root.removeHandler(handler)
        handler.close()

    return uninstall

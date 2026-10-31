# -*- coding: utf-8 -*-
"""Windows 隐藏子进程控制台等平台相关封装。"""

from __future__ import annotations

import subprocess
import sys
from typing import Any


def _windows_startup_kwargs(kwargs: dict[str, Any]) -> dict[str, Any]:
    if sys.platform != "win32":
        return kwargs
    kwargs = dict(kwargs)
    if "creationflags" not in kwargs:
        kwargs["creationflags"] = 0x08000000
    if "startupinfo" not in kwargs:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = startupinfo
    return kwargs


def run_hidden(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    kwargs = _windows_startup_kwargs(kwargs)
    return subprocess.run(cmd, **kwargs)


def popen_hidden(cmd: list[str], **kwargs: Any) -> subprocess.Popen:
    kwargs = _windows_startup_kwargs(kwargs)
    return subprocess.Popen(cmd, **kwargs)

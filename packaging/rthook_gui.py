# -*- coding: utf-8 -*-
"""打包运行时补丁：① 子进程不再闪控制台 ② funasr 在冻结环境里能注册模型类。"""
import sys

if sys.platform == "win32":
    import subprocess

    CREATE_NO_WINDOW = 0x08000000

    _orig_popen_init = subprocess.Popen.__init__

    def _popen_init(self, *args, **kwargs):
        if not kwargs.get("creationflags"):
            kwargs["creationflags"] = CREATE_NO_WINDOW
        if "startupinfo" not in kwargs:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            kwargs["startupinfo"] = startupinfo
        return _orig_popen_init(self, *args, **kwargs)

    subprocess.Popen.__init__ = _popen_init


if getattr(sys, "frozen", False):
    import inspect

    _orig_getsourcelines = inspect.getsourcelines

    def _getsourcelines(obj, *args, **kwargs):
        try:
            return _orig_getsourcelines(obj, *args, **kwargs)
        except Exception:
            return (["# source not bundled\n"], 1)

    inspect.getsourcelines = _getsourcelines

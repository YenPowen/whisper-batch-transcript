#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量提取视频文案 v6 启动入口（源码运行）。"""

import multiprocessing as mp
import os
import sys


if __name__ == "__main__":
    if sys.platform == "win32":
        os.environ.setdefault("PYTHONLEGACYWINDOWSFSENCODING", "1")
    mp.freeze_support()
    from whisper_tool.gui.app import main

    main()

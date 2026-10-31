# -*- coding: utf-8 -*-
"""运行路径与元信息，集中处理源码目录、打包目录和模型目录。"""

from __future__ import annotations

import os
import sys
from pathlib import Path


APP_NAME = "批量提取视频文案"
APP_VERSION = "6.0.0"

PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent


def runtime_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    override = os.environ.get("MEDIA_TOOL_BASE_DIR")
    if override:
        return Path(override).expanduser()
    sibling = PROJECT_ROOT.parent / "models"
    if PROJECT_ROOT.name != "whisper_tool" and sibling.is_dir():
        return PROJECT_ROOT.parent
    return PROJECT_ROOT


BASE_DIR = runtime_base_dir()
MODEL_DIR = BASE_DIR / "models"
CONFIG_FILE = BASE_DIR / "config_v6.json"
LEGACY_CONFIG_FILE = BASE_DIR / "config.json"
LOG_FILE = Path(os.environ.get("MEDIA_TOOL_LOG_FILE", str(Path.home() / "whisper_v6.log")))

ICON_CANDIDATES = (
    BASE_DIR / "图片相关_256x256.ico",
    BASE_DIR / "图片相关_32x32.ico",
    PACKAGE_DIR / "assets" / "app.ico",
)

WHISPER_MODEL_SIZES = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v3-turbo",
)

LANGUAGE_CHOICES = (
    "zh", "en", "ja", "ko", "yue", "fr", "de", "es", "ru", "pt",
    "it", "nl", "pl", "tr", "ar", "vi", "th", "id", "ms", "hi", "auto",
)


def ensure_dirs() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)


def icon_path() -> Path | None:
    for path in ICON_CANDIDATES:
        if path.is_file():
            return path
    return None

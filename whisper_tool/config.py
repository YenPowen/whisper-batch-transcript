# -*- coding: utf-8 -*-
"""应用配置读写与旧版 config.json 自动迁移。"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from . import paths


LOGGER = logging.getLogger(__name__)
CONFIG_VERSION = 2


@dataclass
class AppConfig:
    model_size: str = "base"
    language: str = "zh"
    gpu_fp16: bool = False
    t2s: bool = True
    punctuation: bool = False
    out_txt: bool = True
    out_srt: bool = True
    out_json: bool = False
    initial_prompt: str = ""
    temperature: float = 0.0
    skip_existing: bool = True
    workers: int = 1
    window_size: str = "1120x820"

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        allowed = set(cls.__dataclass_fields__)
        cleaned = {key: value for key, value in data.items() if key in allowed}
        return cls(**cleaned)


def _defaults() -> AppConfig:
    return AppConfig()


def _load_legacy_if_needed(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        if not isinstance(raw, dict):
            return None
        legacy = {
            "model_size": raw.get("model_size"),
            "language": raw.get("lang"),
            "gpu_fp16": raw.get("gpu_fp16"),
            "t2s": raw.get("t2s"),
            "out_txt": raw.get("out_txt"),
            "out_srt": raw.get("out_srt"),
            "out_json": raw.get("out_json"),
        }
        return {key: value for key, value in legacy.items() if value is not None}
    except (OSError, json.JSONDecodeError) as exc:
        LOGGER.warning("读取旧版配置文件失败: %s", exc)
        return None


def load_config() -> AppConfig:
    if paths.CONFIG_FILE.exists():
        try:
            with paths.CONFIG_FILE.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                return AppConfig.from_mapping(data)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.error("读取 %s 失败，使用默认配置: %s", paths.CONFIG_FILE, exc)

    legacy = _load_legacy_if_needed(paths.LEGACY_CONFIG_FILE)
    cfg = _defaults()
    if legacy:
        cfg = AppConfig.from_mapping(legacy)
        LOGGER.info("已从旧版 config.json 迁移设置")
    return cfg


def save_config(cfg: AppConfig) -> bool:
    payload = asdict(cfg)
    payload["version"] = CONFIG_VERSION
    paths.CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".config_v6_",
        suffix=".tmp",
        dir=str(paths.CONFIG_FILE.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
        os.replace(tmp_name, paths.CONFIG_FILE)
        return True
    except OSError as exc:
        LOGGER.error("保存配置失败: %s", exc)
        try:
            Path(tmp_name).unlink(missing_ok=True)
        except OSError:
            pass
        return False

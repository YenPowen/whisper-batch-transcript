# -*- coding: utf-8 -*-
"""ct-punc 标点模型懒加载与自动下载。"""

from __future__ import annotations

import logging
from pathlib import Path

from .. import downloader
from .. import paths


LOGGER = logging.getLogger(__name__)


class PunctuationEngine:
    def __init__(
        self,
        enabled: bool,
        model_dir: Path | None = None,
        device: str = "cpu",
        cancel: object | None = None,
        auto_download: bool = True,
    ) -> None:
        self.enabled = enabled
        self._model_dir = model_dir or (paths.MODEL_DIR / "ct-punc")
        self._device = device
        self._cancel = cancel
        self._auto_download = auto_download
        self._model = None
        self._load_error: Exception | None = None

    def ensure_loaded(self) -> bool:
        if not self.enabled:
            return False
        if self._model is not None:
            return True
        if self._load_error is not None:
            return False
        try:
            if not self._model_dir.is_dir():
                if not self._auto_download:
                    LOGGER.warning("标点模型目录不存在: %s", self._model_dir)
                    return False
                try:
                    downloader.download_punctuation_model(
                        self._model_dir,
                        cancel=self._cancel,
                    )
                except downloader.DownloadError as exc:
                    self._load_error = exc
                    LOGGER.warning("标点模型下载失败，继续转录: %s", exc)
                    return False
            from funasr import AutoModel

            self._model = AutoModel(
                model=str(self._model_dir),
                device=self._device,
            )
            LOGGER.info("ct-punc 标点模型已加载: %s", self._model_dir)
            return True
        except Exception as exc:
            self._load_error = exc
            LOGGER.warning("ct-punc 加载失败，继续转录: %s", exc)
            return False

    def restore(self, text: str) -> str:
        if not self.enabled or self._model is None or not text.strip():
            return text
        try:
            result = self._model.generate(input=text)
            if result and isinstance(result, list):
                first = result[0]
                if isinstance(first, dict):
                    return first.get("text", text)
            return text
        except Exception as exc:
            LOGGER.warning("标点恢复失败，返回原文: %s", exc)
            return text

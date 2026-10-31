# -*- coding: utf-8 -*-
"""文本后处理：繁转简与标点恢复。"""

from __future__ import annotations

import logging

from .punctuator import PunctuationEngine


LOGGER = logging.getLogger(__name__)


class TextProcessor:
    def __init__(
        self,
        t2s: bool = True,
        punctuation_engine: PunctuationEngine | None = None,
    ) -> None:
        self._t2s = t2s
        self._punct = punctuation_engine
        self._converter = None

    def _opencc(self):
        if not self._t2s:
            return None
        if self._converter is not None:
            return self._converter
        try:
            import opencc

            self._converter = opencc.OpenCC("t2s")
        except Exception:
            self._converter = False
            LOGGER.warning("opencc 不可用，繁转简已跳过")
        return self._converter or None

    def process(self, text: str) -> str:
        if not text:
            return text
        result = text
        converter = self._opencc()
        if converter is not None:
            try:
                result = converter.convert(result)
            except Exception:
                LOGGER.exception("繁转简失败")
        if self._punct is not None:
            result = self._punct.restore(result)
        return result

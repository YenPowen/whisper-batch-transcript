# -*- coding: utf-8 -*-
"""Whisper 模型生命周期管理：本地缓存校验、下载、复用与释放。"""

from __future__ import annotations

import gc
import logging
from pathlib import Path
from typing import Any

from .. import downloader
from .. import paths
from .events import DependencyMissingError


LOGGER = logging.getLogger(__name__)

MIN_PLAUSIBLE_BYTES = {
    "tiny": 60 * 1024 * 1024,
    "base": 120 * 1024 * 1024,
    "small": 400 * 1024 * 1024,
    "medium": 1_200 * 1024 * 1024,
    "large-v3-turbo": 1_300 * 1024 * 1024,
}


class WhisperEngine:
    """单进程内持有一个模型；每个后台任务进程独立加载，便于强制终止。"""

    def __init__(
        self,
        model_size: str = "base",
        prefer_gpu: bool = False,
        model_dir: Path | None = None,
        cancel: object | None = None,
    ) -> None:
        self.model_size = model_size
        self.prefer_gpu = prefer_gpu
        self.model_dir = model_dir or paths.MODEL_DIR
        self.cancel = cancel
        self._model: Any = None
        self._checkpoint_path: Path | None = None
        self._device = "cpu"
        self._fp16 = False

    @property
    def device(self) -> str:
        return self._device

    @property
    def fp16(self) -> bool:
        return self._fp16

    @property
    def loaded(self) -> bool:
        return self._model is not None

    def _pick_device(self) -> None:
        if not self.prefer_gpu:
            self._device = "cpu"
            self._fp16 = False
            return
        try:
            import torch

            if torch.cuda.is_available():
                self._device = "cuda"
                self._fp16 = True
                return
        except Exception as exc:
            LOGGER.warning("CUDA 探测失败: %s", exc)
        self._device = "cpu"
        self._fp16 = False
        LOGGER.warning("当前环境没有可用 CUDA，已回退 CPU，fp16 关闭")

    def _local_candidates(self) -> list[Path]:
        size = self.model_size
        return [
            self.model_dir / f"{size}.pt",
            self.model_dir / size / f"{size}.pt",
            Path.home() / ".cache" / "whisper" / size / f"{size}.pt",
        ]

    @staticmethod
    def _plausible(path: Path) -> bool:
        if not path.is_file():
            return False
        min_size = MIN_PLAUSIBLE_BYTES.get(path.parent.name, 0)
        if min_size and path.stat().st_size < min_size:
            for size, expected in MIN_PLAUSIBLE_BYTES.items():
                if path.name == f"{size}.pt" and path.stat().st_size < expected:
                    LOGGER.warning("模型文件疑似损坏（%s，%s 字节），将重新下载", path, path.stat().st_size)
                    return False
        return True

    def _download(self) -> Path:
        target = self.model_dir / f"{self.model_size}.pt"
        urls = downloader.whisper_model_urls(self.model_size)
        last_error: Exception | None = None
        for index, url in enumerate(urls):
            if self.cancel is not None and getattr(self.cancel, "is_set", lambda: False)():
                raise downloader.DownloadCancelled("模型下载已取消")
            try:
                LOGGER.info("模型下载源 %s/%s: %s", index + 1, len(urls), url)
                downloader.download_file(
                    url,
                    target,
                    cancel=self.cancel,
                    retries=2,
                )
                return target
            except downloader.DownloadError as exc:
                last_error = exc
                LOGGER.warning("下载失败，尝试下一镜像: %s", exc)
            except downloader.DownloadCancelled:
                raise
        raise downloader.DownloadError(f"所有模型下载源均失败: {last_error}")

    @staticmethod
    def _looks_like_oom(exc: Exception) -> bool:
        lowered = str(exc).lower()
        return "out of memory" in lowered or "cuda error" in lowered or "cuda out of memory" in lowered

    def load(self) -> "WhisperEngine":
        if self._model is not None:
            return self
        self._pick_device()
        try:
            import whisper
        except ImportError as exc:
            raise DependencyMissingError(
                "未安装 openai-whisper，请先在“模型与依赖”页安装"
            ) from exc

        self.model_dir.mkdir(parents=True, exist_ok=True)
        local_model = next((candidate for candidate in self._local_candidates() if self._plausible(candidate)), None)
        if local_model is not None:
            LOGGER.info("使用本地 Whisper 模型: %s", local_model)
        else:
            local_model = self._download()
        try:
            self._model = whisper.load_model(str(local_model), device=self._device)
        except Exception as exc:
            if self._device == "cuda" and self._looks_like_oom(exc):
                LOGGER.warning("CUDA 显存不足，自动回退 CPU 加载模型")
                self._device = "cpu"
                self._fp16 = False
                self._model = whisper.load_model(str(local_model), device="cpu")
            else:
                raise
        self._checkpoint_path = local_model
        LOGGER.info("Whisper %s 加载完成（%s）", self.model_size, self._device)
        return self

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None,
        initial_prompt: str = "",
        temperature: float | None = None,
    ) -> dict:
        if self._model is None:
            raise RuntimeError("模型尚未加载")
        resolved_language = language
        if resolved_language in (None, "", "auto"):
            resolved_language = None
        options: dict[str, Any] = {
            "language": resolved_language,
            "fp16": self._fp16,
            "verbose": None,
        }
        if initial_prompt:
            options["initial_prompt"] = initial_prompt
        if temperature is not None:
            options["temperature"] = float(temperature)
        try:
            return self._model.transcribe(str(audio_path), **options)
        except Exception as exc:
            if self._device != "cuda" or not self._looks_like_oom(exc):
                raise
            LOGGER.warning("转录时 CUDA 显存不足，回退 CPU 后重试当前文件")
            try:
                import whisper

                self.release()
                self._device = "cpu"
                self._fp16 = False
                if self._checkpoint_path is None:
                    self._checkpoint_path = self._download()
                self._model = whisper.load_model(str(self._checkpoint_path), device="cpu")
                options["fp16"] = False
                return self._model.transcribe(str(audio_path), **options)
            except Exception as retry_exc:
                raise retry_exc from exc

    def release(self) -> None:
        if self._model is None:
            return
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
        except Exception:
            pass
        self._model = None
        gc.collect()

# -*- coding: utf-8 -*-
"""带断点续传、重试与进度回调的模型下载器。"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Callable


LOGGER = logging.getLogger(__name__)

ProgressCallback = Callable[[int, int | None], None]


class DownloadCancelled(Exception):
    pass


class DownloadError(RuntimeError):
    pass


_FALLBACK_URLS = {
    "tiny": "https://openaipublic.azureedge.net/main/whisper/models/65147644a518d12f04e32d6f3b26facc3f8dd46e5390956a9424a650c0ce22b9/tiny.pt",
    "base": "https://openaipublic.azureedge.net/main/whisper/models/ed3a0b6b1c0edf879ad9b11b1af5a0e6ab5db9205f891f668f8b0e6c6326e34e/base.pt",
    "small": "https://openaipublic.azureedge.net/main/whisper/models/9ecf779972d90ba49c06d968637d720dd632c55bbf19d441fb42bf17a411e794/small.pt",
    "medium": "https://openaipublic.azureedge.net/main/whisper/models/345ae4da62f9b3d59415adc60127b97c714f32e89e936602e85993674d08dcb1/medium.pt",
    "large-v3-turbo": "https://openaipublic.azureedge.net/main/whisper/models/aff26ae408abcba5fbf8813c21e62b0941638c5f6eebfb145be0c9839262a19a/large-v3-turbo.pt",
}


def whisper_model_urls(model_size: str) -> list[str]:
    urls: list[str] = []
    try:
        import whisper

        primary = getattr(whisper, "_MODELS", {}).get(model_size)
        if primary:
            urls.append(primary)
    except Exception:
        pass
    fallback = _FALLBACK_URLS.get(model_size)
    if fallback and fallback not in urls:
        urls.append(fallback)
    mirror = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
    mirror_url = f"{mirror}/openai/whisper-{model_size}/resolve/main/{model_size}.pt"
    urls.append(mirror_url)
    return urls


def _cancel_check(cancel: object | None) -> None:
    if cancel is not None and getattr(cancel, "is_set", lambda: False)():
        raise DownloadCancelled("下载已取消")


def _http_session():
    try:
        import requests
    except ImportError as exc:
        raise DownloadError("需要安装 requests 才能自动下载模型") from exc
    return requests


def download_file(
    url: str,
    destination: Path,
    cancel: object | None = None,
    progress: ProgressCallback | None = None,
    retries: int = 3,
    retry_delay: float = 2.0,
) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    requests = _http_session()

    for attempt in range(1, retries + 1):
        _cancel_check(cancel)
        try:
            resume_from = partial.stat().st_size if partial.exists() else 0
            headers = {"User-Agent": "Mozilla/5.0"} | (
                {"Range": f"bytes={resume_from}-"} if resume_from else {}
            )
            with requests.get(url, headers=headers, stream=True, timeout=(15, 60)) as response:
                if response.status_code == 416:
                    partial.unlink(missing_ok=True)
                    continue
                if response.status_code not in (200, 206):
                    raise DownloadError(f"HTTP {response.status_code}，URL: {url}")

                total = int(response.headers.get("Content-Length") or 0) + resume_from
                mode = "ab" if resume_from and response.status_code == 206 else "wb"
                written = resume_from if mode == "ab" else 0
                if mode == "wb":
                    partial.write_bytes(b"")
                with partial.open(mode) as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        _cancel_check(cancel)
                        if not chunk:
                            continue
                        handle.write(chunk)
                        written += len(chunk)
                        if progress:
                            progress(written, total or None)
            os.replace(partial, destination)
            return destination
        except DownloadCancelled:
            raise
        except DownloadError:
            if attempt >= retries:
                raise
        except Exception as exc:
            if attempt >= retries:
                raise DownloadError(f"下载失败（第 {attempt} 次）: {exc}") from exc
        LOGGER.warning("下载第 %s/%s 次失败，%s 秒后重试", attempt, retries, retry_delay)
        time.sleep(retry_delay)
    raise DownloadError(f"超过重试次数: {url}")


PUNCT_MODEL_ID = "iic/punc_ct-transformer_zh-cn-common-vocab272727-pytorch"


def download_punctuation_model(
    target_dir: Path,
    cancel: object | None = None,
    progress: ProgressCallback | None = None,
) -> Path:
    if target_dir.exists() and any(target_dir.iterdir()):
        return target_dir
    try:
        from modelscope.hub.snapshot_download import snapshot_download
    except ImportError as exc:
        raise DownloadError("需要安装 modelscope 才能下载标点模型") from exc
    _cancel_check(cancel)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.info("正在从 ModelScope 下载标点模型")
    if progress:
        progress(0, None)
    try:
        snapshot_download(PUNCT_MODEL_ID, local_dir=str(target_dir))
    except Exception as exc:
        raise DownloadError(f"标点模型下载失败: {exc}") from exc
    if progress:
        progress(1, 1)
    return target_dir

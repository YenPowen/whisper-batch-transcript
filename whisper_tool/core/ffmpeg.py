# -*- coding: utf-8 -*-
"""FFmpeg 探测与统一转码，失败不再悄悄返回原文件。"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

from ..deps import find_ffmpeg_path
from ..platform_utils import popen_hidden
from .events import MediaConversionError, TaskCancelled


def ffmpeg_path() -> str | None:
    return find_ffmpeg_path()


def convert_to_wav(
    input_path: Path,
    wav_path: Path,
    cancel: object | None = None,
    ffmpeg: str | None = None,
    timeout_seconds: float = 60 * 60,
) -> Path:
    executable = ffmpeg or ffmpeg_path()
    if not executable:
        raise MediaConversionError("未找到 ffmpeg，无法解析媒体文件")
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        executable,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-vn",
        "-acodec",
        "pcm_s16le",
        "-ar",
        "16000",
        "-ac",
        "1",
        str(wav_path),
    ]
    try:
        proc = popen_hidden(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except OSError as exc:
        raise MediaConversionError(f"无法启动 ffmpeg: {exc}") from exc

    started = time.monotonic()
    while True:
        if proc.poll() is not None:
            break
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            proc.terminate()
            raise TaskCancelled("转换音频时已取消")
        if time.monotonic() - started > timeout_seconds:
            proc.terminate()
            raise MediaConversionError("ffmpeg 转换超时")
        time.sleep(0.1)

    _stdout, stderr = proc.communicate(timeout=10)
    if proc.returncode != 0 or not wav_path.is_file() or wav_path.stat().st_size <= 1024:
        tail = (stderr or b"").decode("utf-8", errors="replace").strip().splitlines()[-5:]
        detail = "；".join(tail)
        raise MediaConversionError(f"ffmpeg 转码失败，退出码 {proc.returncode} {detail}".strip())
    return wav_path

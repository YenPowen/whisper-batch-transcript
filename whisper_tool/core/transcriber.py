# -*- coding: utf-8 -*-
"""单文件/批量的转写流程：转换、识别、文本后处理与导出分离。"""

from __future__ import annotations

import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .events import BatchResult, MediaConversionError, Reporter, TaskCancelled
from .exporter import ExportOptions, expected_files, write_transcription_outputs
from .ffmpeg import convert_to_wav
from .model_manager import WhisperEngine
from .text import TextProcessor


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscribeOptions:
    language: str = "zh"
    initial_prompt: str = ""
    temperature: float = 0.0
    t2s: bool = True
    punctuation: bool = True
    skip_existing: bool = True
    out_txt: bool = True
    out_srt: bool = True
    out_json: bool = False

    def export_options(self) -> ExportOptions:
        return ExportOptions(
            out_txt=self.out_txt,
            out_srt=self.out_srt,
            out_json=self.out_json,
        )


def _unique_subdir_name(media: Path, output_root: Path, occupied: set[str]) -> Path:
    base = media.stem or "media"
    candidate = base
    counter = 2
    while candidate in occupied:
        candidate = f"{base}_{counter}"
        counter += 1
    occupied.add(candidate)
    return output_root / candidate


def transcribe_batch(
    media_files: list[str | Path],
    output_root: Path,
    engine: WhisperEngine,
    options: TranscribeOptions,
    reporter: Reporter | None = None,
    cancel: object | None = None,
    punctuator=None,
) -> BatchResult:
    reporter = reporter or Reporter()
    result = BatchResult()
    export_options = options.export_options()
    if not (export_options.out_txt or export_options.out_srt or export_options.out_json):
        raise ValueError("至少需要选择 TXT、SRT 或 JSON 中的一种输出格式")

    output_root.mkdir(parents=True, exist_ok=True)
    temp_root = output_root / f".tmp_audio_{int(time.time())}_{uuid4().hex[:6]}"
    temp_root.mkdir(parents=True, exist_ok=True)
    processor = TextProcessor(t2s=options.t2s, punctuation_engine=punctuator)
    occupied: set[str] = set()

    try:
        total = len(media_files)
        for index, media_path in enumerate(media_files, start=1):
            if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                result.cancelled = True
                LOGGER.warning("转录任务已取消")
                break
            media = Path(media_path)
            if not media.is_file():
                LOGGER.error("[%s/%s] 文件不存在: %s", index, total, media)
                result.failed += 1
                continue
            subdir = _unique_subdir_name(media, output_root, occupied)
            expected = expected_files(media.stem, subdir, export_options)
            if options.skip_existing and all(path.is_file() for path in expected):
                LOGGER.info("[%s/%s] %s 的输出已存在，跳过", index, total, media.name)
                result.skipped += 1
                result.success += 1
                reporter.progress(index / total * 100)
                continue

            reporter.status(f"正在处理 {index}/{total}: {media.name}")
            wav_path = temp_root / f"{index:03d}_{uuid4().hex[:8]}.wav"
            try:
                LOGGER.info("[%s/%s] 开始处理 %s", index, total, media.name)
                convert_to_wav(media, wav_path, cancel=cancel)
                transcript = engine.transcribe(
                    wav_path,
                    language=options.language,
                    initial_prompt=options.initial_prompt,
                    temperature=options.temperature,
                )
                if cancel is not None and getattr(cancel, "is_set", lambda: False)():
                    result.cancelled = True
                    break
                write_transcription_outputs(
                    media.stem,
                    subdir,
                    transcript,
                    export_options,
                    processor,
                )
                result.success += 1
                LOGGER.info("[%s/%s] %s 转录完成", index, total, media.name)
            except TaskCancelled:
                result.cancelled = True
                break
            except MediaConversionError as exc:
                result.failed += 1
                LOGGER.error("[%s/%s] %s 转码失败: %s", index, total, media.name, exc)
            except Exception as exc:
                result.failed += 1
                LOGGER.error("[%s/%s] %s 转录失败: %s", index, total, media.name, exc)
                LOGGER.debug("转录失败详情", exc_info=True)
            finally:
                try:
                    wav_path.unlink(missing_ok=True)
                except OSError:
                    pass
                reporter.progress(index / total * 100)
    finally:
        try:
            shutil.rmtree(temp_root, ignore_errors=True)
        except OSError:
            pass
    return result

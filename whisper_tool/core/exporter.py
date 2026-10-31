# -*- coding: utf-8 -*-
"""TXT/SRT/JSON 导出与 SRT 时间格式。"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExportOptions:
    out_txt: bool = True
    out_srt: bool = True
    out_json: bool = False


def format_time(seconds: float) -> str:
    total_ms = max(0, int(round(seconds * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, ms = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def expected_files(stem: str, subdir: Path, options: ExportOptions) -> list[Path]:
    files: list[Path] = []
    if options.out_txt:
        files.append(subdir / f"{stem}.txt")
    if options.out_srt:
        files.append(subdir / f"{stem}.srt")
    if options.out_json:
        files.append(subdir / f"{stem}.json")
    return files


def _atomic_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)


def write_transcription_outputs(
    stem: str,
    subdir: Path,
    result: dict,
    options: ExportOptions,
    text_processor,
) -> list[Path]:
    written: list[Path] = []
    subdir.mkdir(parents=True, exist_ok=True)
    full_text = text_processor.process((result.get("text") or "").strip())

    if options.out_txt:
        target = subdir / f"{stem}.txt"
        _atomic_text(target, full_text)
        written.append(target)

    if options.out_srt:
        target = subdir / f"{stem}.srt"
        lines: list[str] = []
        for seg in result.get("segments") or []:
            seg_text = text_processor.process((seg.get("text") or "").strip())
            lines.append(f"{int(seg.get('id', 0)) + 1}")
            lines.append(f"{format_time(float(seg.get('start', 0)))} --> {format_time(float(seg.get('end', 0)))}")
            lines.append(seg_text)
            lines.append("")
        _atomic_text(target, "\n".join(lines))
        written.append(target)

    if options.out_json:
        target = subdir / f"{stem}.json"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, target)
        written.append(target)
    return written

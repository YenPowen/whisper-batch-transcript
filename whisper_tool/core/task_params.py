# -*- coding: utf-8 -*-
"""可跨进程传递的任务参数。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TaskParams:
    mode: str  # transcribe | summary | full
    media_files: tuple[str, ...] = ()
    output_root: str = ""
    excel_path: str = ""
    model_size: str = "base"
    language: str = "zh"
    gpu_fp16: bool = False
    t2s: bool = True
    punctuation: bool = False
    out_txt: bool = True
    out_srt: bool = True
    out_json: bool = False
    skip_existing: bool = True
    initial_prompt: str = ""
    temperature: float = 0.0
    workers: int = 1

# -*- coding: utf-8 -*-
"""可被 multiprocessing.Process 调用的任务入口。"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from pathlib import Path

from .. import deps
from .. import logging_utils
from .events import DependencyMissingError, Reporter, TaskCancelled
from .model_manager import WhisperEngine
from .punctuator import PunctuationEngine
from .summarizer import summarize_to_excel
from .task_params import TaskParams
from .transcriber import TranscribeOptions, transcribe_batch


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskOutcome:
    ok: bool
    message: str
    success: int = 0
    failed: int = 0
    skipped: int = 0
    cancelled: bool = False


def _device_for(params: TaskParams) -> str:
    report = deps.scan(include_torch=True)
    return "cuda" if params.gpu_fp16 and report.torch_cuda else "cpu"


def _run_transcribe(
    params: TaskParams,
    reporter: Reporter,
    cancel: object,
) -> TaskOutcome:
    engine = WhisperEngine(
        model_size=params.model_size,
        prefer_gpu=params.gpu_fp16,
        cancel=cancel,
    )
    device = _device_for(params)
    punct = PunctuationEngine(
        enabled=params.punctuation,
        device=device,
        cancel=cancel,
    )
    try:
        reporter.status("正在加载 Whisper 模型...")
        engine.load()
        if params.punctuation:
            reporter.status("正在加载标点恢复模型...")
            punct.ensure_loaded()
    except DependencyMissingError as exc:
        return TaskOutcome(ok=False, message=str(exc))
    except Exception as exc:
        LOGGER.exception("模型加载失败")
        return TaskOutcome(ok=False, message=f"模型加载失败: {exc}")

    options = TranscribeOptions(
        language=params.language,
        initial_prompt=params.initial_prompt,
        temperature=params.temperature,
        t2s=params.t2s,
        punctuation=params.punctuation,
        skip_existing=params.skip_existing,
        out_txt=params.out_txt,
        out_srt=params.out_srt,
        out_json=params.out_json,
    )
    try:
        outcome = transcribe_batch(
            list(params.media_files),
            Path(params.output_root),
            engine,
            options,
            reporter=reporter,
            cancel=cancel,
            punctuator=punct,
        )
    except TaskCancelled:
        outcome = None
    if outcome is None or outcome.cancelled:
        return TaskOutcome(
            ok=False,
            cancelled=True,
            success=getattr(outcome, "success", 0),
            failed=getattr(outcome, "failed", 0),
            message="转录任务已取消",
        )
    return TaskOutcome(
        ok=True,
        message=f"转录结束，成功 {outcome.success}，失败 {outcome.failed}，跳过 {outcome.skipped}",
        success=outcome.success,
        failed=outcome.failed,
        skipped=outcome.skipped,
    )


def _run_summary(params: TaskParams, reporter: Reporter, cancel: object) -> TaskOutcome:
    reporter.status("正在汇总 TXT 到 Excel...")
    try:
        ok = summarize_to_excel(
            Path(params.output_root),
            Path(params.excel_path),
            t2s=params.t2s,
            progress_callback=lambda value: reporter.progress(value),
            cancel=cancel,
        )
        return TaskOutcome(ok=ok, message="Excel 汇总完成" if ok else "Excel 汇总失败")
    except DependencyMissingError as exc:
        return TaskOutcome(ok=False, message=str(exc))
    except Exception:
        LOGGER.exception("汇总任务异常")
        return TaskOutcome(ok=False, message="汇总任务异常，详见日志")


def execute_task(params: TaskParams, cancel: object, reporter: Reporter) -> TaskOutcome:
    if params.mode == "summary":
        return _run_summary(params, reporter, cancel)
    transcription = _run_transcribe(params, reporter, cancel)
    if params.mode == "transcribe" or not transcription.ok or transcription.cancelled:
        return transcription
    summary_params = TaskParams(
        mode="summary",
        output_root=params.output_root,
        excel_path=params.excel_path,
        t2s=params.t2s,
        workers=1,
    )
    return _run_summary(summary_params, reporter, cancel)


def worker_entry(params: TaskParams, cancel, queue) -> None:
    uninstall = logging_utils.install_queue_logging(queue)
    reporter = Reporter(queue)
    try:
        outcome = execute_task(params, cancel, reporter)
        queue.put(
            {
                "kind": "done",
                "ok": outcome.ok,
                "message": outcome.message,
                "success": outcome.success,
                "failed": outcome.failed,
                "skipped": outcome.skipped,
                "cancelled": outcome.cancelled,
            },
            timeout=20,
        )
    except Exception:
        LOGGER.error("任务进程发生未处理异常:\n%s", traceback.format_exc())
        queue.put(
            {"kind": "error", "message": traceback.format_exc()},
            timeout=20,
        )
    finally:
        try:
            uninstall()
        except Exception:
            pass

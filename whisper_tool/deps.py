# -*- coding: utf-8 -*-
"""可选依赖检测与安装提示，不再把几十个全局布尔值散落在主程序里。"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import logging
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import paths
from .platform_utils import run_hidden


LOGGER = logging.getLogger(__name__)

PIP_MIRROR_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"


@dataclass(frozen=True)
class DependencyReport:
    whisper_version: str | None
    opencc: bool
    pandas: bool
    openpyxl: bool
    funasr: bool
    modelscope: bool
    torch_cuda: bool
    torch_installed: bool
    ffmpeg_path: str | None

    @property
    def excel_ok(self) -> bool:
        return self.pandas and self.openpyxl

    @property
    def transcribe_ok(self) -> bool:
        return bool(self.whisper_version and self.ffmpeg_path)


def _module_version(module_name: str, dist_name: str | None = None) -> str | None:
    if not importlib.util.find_spec(module_name):
        return None
    try:
        return importlib.metadata.version(dist_name or module_name)
    except importlib.metadata.PackageNotFoundError:
        try:
            module = __import__(module_name)
            return getattr(module, "__version__", "installed")
        except Exception:
            return "installed"


def find_ffmpeg_path() -> str | None:
    candidates = [
        paths.BASE_DIR / "ffmpeg.exe",
        paths.PROJECT_ROOT / "ffmpeg.exe",
        paths.PACKAGE_DIR.parent / "ffmpeg.exe",
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    found = shutil.which("ffmpeg")
    if found:
        return found
    return None


def scan(include_torch: bool = True) -> DependencyReport:
    torch_installed = importlib.util.find_spec("torch") is not None
    cuda = False
    if include_torch and torch_installed:
        try:
            import torch

            cuda = bool(torch.cuda.is_available())
        except Exception as exc:
            LOGGER.warning("探测 CUDA 失败: %s", exc)
    return DependencyReport(
        whisper_version=_module_version("whisper", "openai-whisper"),
        opencc=importlib.util.find_spec("opencc") is not None,
        pandas=importlib.util.find_spec("pandas") is not None,
        openpyxl=importlib.util.find_spec("openpyxl") is not None,
        funasr=importlib.util.find_spec("funasr") is not None,
        modelscope=importlib.util.find_spec("modelscope") is not None,
        torch_cuda=cuda,
        torch_installed=torch_installed,
        ffmpeg_path=find_ffmpeg_path(),
    )


def missing_packages(report: DependencyReport, mode: str) -> list[str]:
    missing: list[str] = []
    if mode in {"transcribe", "full"}:
        if not report.whisper_version:
            missing.append("openai-whisper")
        if not report.opencc:
            missing.append("OpenCC")
    if mode in {"summary", "full"} and not report.excel_ok:
        if not report.pandas:
            missing.append("pandas")
        if not report.openpyxl:
            missing.append("openpyxl")
    return missing


def install_packages(
    packages: Iterable[str],
    mirror: bool = True,
    timeout: int = 600,
) -> tuple[bool, str]:
    names = sorted(set(packages))
    if not names:
        return True, ""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check"]
    if mirror:
        cmd += ["--index-url", PIP_MIRROR_URL]
    cmd += names
    LOGGER.info("开始安装依赖: %s", " ".join(names))
    try:
        proc = run_hidden(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        tail = "\n".join((proc.stdout or "").strip().splitlines()[-20:])
        return proc.returncode == 0, tail
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def dependency_summary(report: DependencyReport) -> str:
    parts = []
    if report.transcribe_ok:
        parts.append(f"Whisper {report.whisper_version}")
    else:
        parts.append("Whisper 未安装")
    if report.ffmpeg_path:
        parts.append("FFmpeg 就绪")
    else:
        parts.append("FFmpeg 缺失")
    parts.append("繁简转换: " + ("可用" if report.opencc else "未安装"))
    parts.append("Excel: " + ("可用" if report.excel_ok else "缺少 pandas/openpyxl"))
    parts.append("标点: " + ("funasr 已安装" if report.funasr else "funasr 未安装"))
    if report.torch_cuda:
        parts.append("CUDA 可用")
    elif report.torch_installed:
        parts.append("CPU 模式")
    return " | ".join(parts)

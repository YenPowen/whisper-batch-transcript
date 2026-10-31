# -*- coding: utf-8 -*-
"""v6 主窗口：响应式布局、模型管理页与搜索日志面板。"""

from __future__ import annotations

import logging
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .. import deps
from .. import downloader
from .. import logging_utils
from .. import paths
from ..config import AppConfig, load_config, save_config
from ..core.task_params import TaskParams
from .log_panel import LogPanel
from .task_controller import TaskController


LOGGER = logging.getLogger(__name__)

BG = "#eef2f7"
PANEL = "#ffffff"
ACCENT = "#2563eb"
TEXT = "#0f172a"

MODEL_LABELS = [
    ("tiny", "tiny 极速"),
    ("base", "base 平衡"),
    ("small", "small 精度"),
    ("medium", "medium 高精度"),
    ("large-v3-turbo", "large-v3-turbo 超精度"),
]


class WhisperApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"{paths.APP_NAME} v{paths.APP_VERSION}")
        self.root.configure(bg=BG)
        icon = paths.icon_path()
        if icon:
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError as exc:
                LOGGER.warning("加载图标失败: %s", exc)

        self.cfg = load_config()
        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="就绪")
        self._running = False
        self._last_context: dict[str, str] = {}
        self._download_cancel = threading.Event()
        self._download_busy = False
        self._first_dep_check = True
        self.deps = deps.scan(include_torch=False)

        self.controller = TaskController(
            root,
            on_log=self.log,
            on_progress=lambda value: self.progress_var.set(max(0, min(100, value))),
            on_status=lambda text: self.status_var.set(text),
            on_finished=self.on_task_finished,
        )
        self._build_vars()
        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.log("INFO", f"{paths.APP_NAME} v{paths.APP_VERSION} 已启动")
        self.refresh_dependencies(defer_heavy=True)

    def _build_vars(self) -> None:
        labels = {size: label for size, label in MODEL_LABELS}
        self.model_size = self.cfg.model_size if self.cfg.model_size in labels else "base"
        self.model_label = tk.StringVar(value=labels[self.model_size])
        self.language_var = tk.StringVar(value=self.cfg.language)
        self.t2s_var = tk.BooleanVar(value=self.cfg.t2s)
        self.gpu_var = tk.BooleanVar(value=self.cfg.gpu_fp16)
        self.punct_var = tk.BooleanVar(value=self.cfg.punctuation)
        self.out_txt_var = tk.BooleanVar(value=self.cfg.out_txt)
        self.out_srt_var = tk.BooleanVar(value=self.cfg.out_srt)
        self.out_json_var = tk.BooleanVar(value=self.cfg.out_json)
        self.skip_var = tk.BooleanVar(value=self.cfg.skip_existing)
        self.temperature_var = tk.StringVar(value=f"{self.cfg.temperature:g}")
        self.prompt_var = tk.StringVar(value=self.cfg.initial_prompt)

    def _build_ui(self) -> None:
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self.root, bg=PANEL, height=64)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(1, weight=1)
        tk.Label(
            header,
            text=paths.APP_NAME,
            font=("Microsoft YaHei UI", 16, "bold"),
            bg=PANEL,
            fg=TEXT,
        ).grid(row=0, column=0, padx=(18, 8), pady=12)
        tk.Label(
            header,
            text=f"v{paths.APP_VERSION}",
            font=("Microsoft YaHei UI", 9),
            bg=PANEL,
            fg="#64748b",
        ).grid(row=0, column=1, sticky="w")
        self.header_deps = tk.Label(
            header,
            text="",
            bg=PANEL,
            fg="#475569",
            font=("Microsoft YaHei UI", 9),
        )
        self.header_deps.grid(row=0, column=2, padx=16, sticky="e")

        self.notebook = ttk.Notebook(self.root)
        self.notebook.grid(row=1, column=0, sticky="nsew", padx=12, pady=(10, 0))
        self.task_page = ttk.Frame(self.notebook, padding=12)
        self.model_page = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.task_page, text="转录任务")
        self.notebook.add(self.model_page, text="模型与依赖")

        self._build_task_tab()
        self._build_model_tab()

        self.log_panel = LogPanel(self.root, title="运行日志")
        self.log_panel.grid(row=2, column=0, sticky="nsew", padx=12, pady=(8, 6))
        self.root.grid_rowconfigure(2, weight=1)
        self.root.grid_rowconfigure(1, weight=1)

        status_bar = tk.Frame(self.root, bg="#dbe3ed", height=28)
        status_bar.grid(row=3, column=0, sticky="ew")
        tk.Label(
            status_bar,
            textvariable=self.status_var,
            anchor="w",
            bg="#dbe3ed",
            fg=TEXT,
            font=("Microsoft YaHei UI", 9),
        ).pack(side="left", padx=12)

        window_w, window_h = self._parse_window_size(self.cfg.window_size)
        self.root.geometry(f"{window_w}x{window_h}")
        self.root.minsize(1000, 700)
        self.root.update_idletasks()

    @staticmethod
    def _parse_window_size(value: str) -> tuple[int, int]:
        try:
            width, height = value.lower().split("x")
            return max(1000, int(width)), max(700, int(height))
        except Exception:
            return 1160, 860

    def _build_task_tab(self) -> None:
        settings = ttk.LabelFrame(self.task_page, text="识别设置", padding=12)
        settings.pack(fill="x")
        settings.columnconfigure(3, weight=1)

        ttk.Label(settings, text="模型").grid(row=0, column=0, sticky="w", padx=(0, 6), pady=4)
        model_combo = ttk.Combobox(
            settings,
            textvariable=self.model_label,
            values=[label for _size, label in MODEL_LABELS],
            state="readonly",
            width=22,
        )
        model_combo.grid(row=0, column=1, sticky="w", pady=4)
        self.gpu_check = ttk.Checkbutton(settings, text="GPU 加速 (fp16)", variable=self.gpu_var)
        self.gpu_check.grid(row=0, column=2, sticky="w", padx=(18, 0), pady=4)

        ttk.Label(settings, text="语言").grid(row=1, column=0, sticky="w", padx=(0, 6), pady=4)
        lang_combo = ttk.Combobox(
            settings,
            textvariable=self.language_var,
            values=list(paths.LANGUAGE_CHOICES),
            width=20,
        )
        lang_combo.grid(row=1, column=1, sticky="w", pady=4)
        self.t2s_check = ttk.Checkbutton(settings, text="繁转简", variable=self.t2s_var)
        self.t2s_check.grid(row=1, column=2, sticky="w", padx=(18, 0), pady=4)
        self.punct_check = ttk.Checkbutton(
            settings,
            text="中文标点恢复 (ct-punc)",
            variable=self.punct_var,
        )
        self.punct_check.grid(row=1, column=3, sticky="w", pady=4)

        advanced = ttk.LabelFrame(self.task_page, text="高级选项", padding=12)
        advanced.pack(fill="x", pady=(10, 8))
        advanced.columnconfigure(1, weight=1)
        advanced.columnconfigure(3, weight=2)
        ttk.Label(advanced, text="温度").grid(row=0, column=0, padx=(0, 6))
        ttk.Spinbox(
            advanced,
            from_=0,
            to=1,
            increment=0.1,
            textvariable=self.temperature_var,
            width=7,
        ).grid(row=0, column=1, sticky="w")
        ttk.Label(advanced, text="初始提示").grid(row=0, column=2, padx=(16, 6))
        ttk.Entry(advanced, textvariable=self.prompt_var).grid(row=0, column=3, sticky="ew")
        self.skip_check = ttk.Checkbutton(advanced, text="跳过已有输出", variable=self.skip_var)
        self.skip_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        formats = ttk.LabelFrame(self.task_page, text="输出格式", padding=12)
        formats.pack(fill="x")
        self.out_txt_check = ttk.Checkbutton(formats, text="TXT", variable=self.out_txt_var)
        self.out_txt_check.pack(side="left", padx=(4, 18))
        self.out_srt_check = ttk.Checkbutton(formats, text="SRT 字幕", variable=self.out_srt_var)
        self.out_srt_check.pack(side="left", padx=(0, 18))
        self.out_json_check = ttk.Checkbutton(formats, text="JSON", variable=self.out_json_var)
        self.out_json_check.pack(side="left")

        buttons = tk.Frame(self.task_page, bg=BG)
        buttons.pack(fill="x", pady=(12, 8))
        for column in range(4):
            buttons.columnconfigure(column, weight=1)
        self.btn_full = tk.Button(
            buttons,
            text="完整流程（转录+汇总）",
            bg=ACCENT,
            fg="white",
            activebackground="#1d4ed8",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.run_full,
        )
        self.btn_full.grid(row=0, column=0, sticky="ew", padx=(0, 3), ipady=7)
        self.btn_trans = tk.Button(
            buttons,
            text="仅转录",
            bg="#0e7490",
            fg="white",
            activebackground="#155e75",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.run_transcribe_only,
        )
        self.btn_trans.grid(row=0, column=1, sticky="ew", padx=3, ipady=7)
        self.btn_summary = tk.Button(
            buttons,
            text="仅汇总",
            bg="#15803d",
            fg="white",
            activebackground="#166534",
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.run_summary_only,
        )
        self.btn_summary.grid(row=0, column=2, sticky="ew", padx=3, ipady=7)
        self.btn_stop = tk.Button(
            buttons,
            text="停止任务",
            bg="#dc2626",
            fg="white",
            activebackground="#991b1b",
            activeforeground="white",
            relief="flat",
            state="disabled",
            cursor="hand2",
            command=self.stop_task,
        )
        self.btn_stop.grid(row=0, column=3, sticky="ew", padx=(3, 0), ipady=7)

        progress_box = ttk.Frame(self.task_page)
        progress_box.pack(fill="x")
        ttk.Progressbar(progress_box, variable=self.progress_var, maximum=100).pack(fill="x")
        ttk.Label(progress_box, textvariable=self.status_var).pack(anchor="w", pady=(4, 0))

    def _build_model_tab(self) -> None:
        self.model_page.columnconfigure(0, weight=1)
        deps_frame = ttk.LabelFrame(self.model_page, text="依赖状态", padding=10)
        deps_frame.grid(row=0, column=0, sticky="ew")
        deps_frame.columnconfigure(1, weight=1)
        self._dep_labels: dict[str, tk.Label] = {}
        components = [
            ("whisper", "Whisper 识别"),
            ("ffmpeg", "FFmpeg"),
            ("opencc", "繁转简 (OpenCC)"),
            ("excel", "Excel (pandas/openpyxl)"),
            ("punct", "标点 (funasr)"),
            ("gpu", "GPU"),
        ]
        for index, (key, text) in enumerate(components):
            ttk.Label(deps_frame, text=text).grid(row=index, column=0, sticky="w", padx=(0, 12), pady=2)
            label = tk.Label(deps_frame, text="检测中...", bg=PANEL, fg="#64748b")
            label.grid(row=index, column=1, sticky="w")
            self._dep_labels[key] = label
        self.btn_install = tk.Button(
            deps_frame,
            text="安装缺失依赖",
            bg="#475569",
            fg="white",
            relief="flat",
            command=self.install_missing_deps,
        )
        self.btn_install.grid(row=len(components), column=0, columnspan=2, sticky="w", pady=(8, 0))

        download_frame = ttk.LabelFrame(self.model_page, text="模型下载", padding=10)
        download_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        download_frame.columnconfigure(1, weight=1)
        self.download_label_var = tk.StringVar(value=MODEL_LABELS[-1][1])
        ttk.Label(download_frame, text="Whisper 模型").grid(row=0, column=0, sticky="w")
        self.download_combo = ttk.Combobox(
            download_frame,
            textvariable=self.download_label_var,
            values=[label for _size, label in MODEL_LABELS],
            state="readonly",
            width=28,
        )
        self.download_combo.grid(row=0, column=1, sticky="w", padx=10)
        self.btn_download_model = tk.Button(
            download_frame,
            text="下载/续传",
            bg=ACCENT,
            fg="white",
            relief="flat",
            command=self.download_whisper_model,
        )
        self.btn_download_model.grid(row=0, column=2, sticky="e")
        self.btn_cancel_download = tk.Button(
            download_frame,
            text="取消下载",
            bg="#dc2626",
            fg="white",
            relief="flat",
            state="disabled",
            command=self.cancel_download,
        )
        self.btn_cancel_download.grid(row=0, column=3, sticky="e", padx=(6, 0))

        self.download_progress_var = tk.DoubleVar(value=0)
        self.download_status_var = tk.StringVar(value="未开始")
        ttk.Progressbar(
            download_frame,
            variable=self.download_progress_var,
            maximum=100,
        ).grid(row=1, column=0, columnspan=4, sticky="ew", pady=(8, 2))
        ttk.Label(download_frame, textvariable=self.download_status_var).grid(
            row=2, column=0, columnspan=4, sticky="w"
        )

        action_row = ttk.Frame(self.model_page)
        action_row.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        action_row.columnconfigure(0, weight=1)
        self.btn_punct_download = tk.Button(
            action_row,
            text="下载标点模型 ct-punc",
            bg="#7c3aed",
            fg="white",
            relief="flat",
            command=self.download_punctuation,
        )
        self.btn_punct_download.pack(side="left")
        self.btn_clean = tk.Button(
            action_row,
            text="清理 Whisper 模型缓存",
            bg="#b91c1c",
            fg="white",
            relief="flat",
            command=self.clean_model_cache,
        )
        self.btn_clean.pack(side="right")
        self.model_page.grid_rowconfigure(3, weight=1)

    def log(self, level: str, message: str) -> None:
        if str(level).upper() in {"SUCCESS", "SUCC"}:
            LOGGER.log(logging_utils.SUCCESS, "%s", message)
        else:
            LOGGER.log(getattr(logging, level.upper(), logging.INFO), "%s", message)
        self.log_panel.append(level, message)

    def refresh_dependencies(self, defer_heavy: bool = True) -> None:
        if defer_heavy:
            threading.Thread(target=self._heavy_dependency_refresh, daemon=True).start()
        else:
            self._apply_dependencies(deps.scan(include_torch=True))

    def _heavy_dependency_refresh(self) -> None:
        try:
            report = deps.scan(include_torch=True)
            self.root.after(0, lambda: self._apply_dependencies(report))
        except Exception as exc:
            LOGGER.warning("依赖扫描失败: %s", exc)

    def _apply_dependencies(self, report: deps.DependencyReport) -> None:
        self.deps = report
        values: dict[str, str] = {
            "whisper": report.whisper_version or "未安装",
            "ffmpeg": "就绪" if report.ffmpeg_path else "未找到",
            "opencc": "可用" if report.opencc else "未安装",
            "excel": "可用" if report.excel_ok else "缺少组件",
            "punct": "可用" if report.funasr else "未安装",
            "gpu": "CUDA 可用" if report.torch_cuda else ("CPU" if report.torch_installed else "torch 未安装"),
        }
        for key, label in self._dep_labels.items():
            text = values[key]
            label.configure(text=text, fg="#15803d" if "可用" in text or "就绪" in text else "#dc2626")
        self.header_deps.configure(text=deps.dependency_summary(report))
        if self._first_dep_check:
            self._first_dep_check = False
            if not report.transcribe_ok:
                self.root.after(600, self._prompt_first_run_dependencies)

    def _prompt_first_run_dependencies(self) -> None:
        if self._running or self._download_busy:
            return
        missing: list[str] = []
        if not self.deps.whisper_version:
            missing.append("openai-whisper")
        if not self.deps.ffmpeg_path:
            missing.append("FFmpeg")
        if not missing:
            return
        has_ffmpeg = "FFmpeg" not in missing
        if not has_ffmpeg:
            messagebox.showwarning(
                "缺少 FFmpeg",
                "未找到 FFmpeg。请把 ffmpeg.exe（以及 ffprobe.exe）放到程序目录，"
                "或加入系统 PATH 后重启程序。",
            )
        if any(name != "FFmpeg" for name in missing):
            if messagebox.askyesno(
                "首次依赖检查",
                "未检测到：\n" + "\n".join(name for name in missing if name != "FFmpeg") + "\n\n是否打开依赖安装？",
            ):
                self.notebook.select(self.model_page)
                self.install_missing_deps()

    def _selected_model_size(self) -> str:
        selected = self.model_label.get()
        for size, label in MODEL_LABELS:
            if label == selected:
                return size
        return "base"

    def _params(self, mode: str, media: tuple[str, ...], output_root: str, excel_path: str = "") -> TaskParams:
        return TaskParams(
            mode=mode,
            media_files=media,
            output_root=output_root,
            excel_path=excel_path,
            model_size=self._selected_model_size(),
            language=self.language_var.get().strip() or "auto",
            gpu_fp16=self.gpu_var.get(),
            t2s=self.t2s_var.get(),
            punctuation=self.punct_var.get(),
            out_txt=self.out_txt_var.get(),
            out_srt=self.out_srt_var.get(),
            out_json=self.out_json_var.get(),
            skip_existing=self.skip_var.get(),
            initial_prompt=self.prompt_var.get().strip(),
            temperature=float(self.temperature_var.get() or 0),
        )

    def _save_settings(self) -> None:
        self.cfg = AppConfig(
            model_size=self._selected_model_size(),
            language=self.language_var.get().strip() or "auto",
            gpu_fp16=self.gpu_var.get(),
            t2s=self.t2s_var.get(),
            punctuation=self.punct_var.get(),
            out_txt=self.out_txt_var.get(),
            out_srt=self.out_srt_var.get(),
            out_json=self.out_json_var.get(),
            initial_prompt=self.prompt_var.get().strip(),
            temperature=float(self.temperature_var.get() or 0),
            skip_existing=self.skip_var.get(),
            window_size=f"{self.root.winfo_width()}x{self.root.winfo_height()}",
        )
        save_config(self.cfg)

    def _ask_missing_deps(self, required_report: deps.DependencyReport, mode: str) -> bool:
        missing = deps.missing_packages(required_report, mode)
        problems: list[str] = []
        if mode in {"transcribe", "full"} and not required_report.ffmpeg_path:
            problems.append("未找到 FFmpeg，请将 ffmpeg.exe 放在程序目录或加入 PATH")
        if mode in {"transcribe", "full"} and not required_report.whisper_version:
            problems.append("需要安装 openai-whisper")
        if mode in {"summary", "full"} and not required_report.excel_ok:
            problems.append("需要 pandas 与 openpyxl")
        if not problems and not missing:
            return True
        detail = "\n".join(problems)
        proceed = messagebox.askyesno(
            "缺少依赖",
            f"当前缺少以下组件：\n{detail}\n\n是否打开依赖安装？",
        )
        if proceed:
            self.notebook.select(self.model_page)
            self.install_missing_deps()
        return False

    def _select_media(self) -> tuple[str, ...]:
        files = filedialog.askopenfilenames(
            title="选择视频或音频文件",
            filetypes=[
                ("媒体文件", "*.mp4 *.avi *.mov *.mkv *.webm *.mp3 *.wav *.m4a *.flac *.aac *.ogg *.wma"),
                ("所有文件", "*.*"),
            ],
        )
        return tuple(files)

    def _select_dir(self, title: str) -> str:
        return filedialog.askdirectory(title=title) or ""

    def run_transcribe_only(self) -> None:
        if not self._ask_missing_deps(self.deps, "transcribe"):
            return
        media = self._select_media()
        if not media:
            return
        out_root = self._select_dir("选择转录结果保存目录")
        if not out_root:
            return
        self._start_task(self._params("transcribe", media, out_root), out_root)

    def run_summary_only(self) -> None:
        if not self._ask_missing_deps(self.deps, "summary"):
            return
        source = self._select_dir("选择包含 TXT 的根目录")
        if not source:
            return
        default_name = f"转录汇总_{Path(source).name}.xlsx"
        excel = filedialog.asksaveasfilename(
            title="保存 Excel 汇总",
            initialfile=default_name,
            defaultextension=".xlsx",
            filetypes=[("Excel 表格", "*.xlsx")],
        )
        if not excel:
            return
        self._start_task(self._params("summary", (), source, excel), excel)

    def run_full(self) -> None:
        if not self.out_txt_var.get():
            if messagebox.askyesno("需要 TXT", "Excel 汇总读取 TXT 文件，是否同时导出 TXT？"):
                self.out_txt_var.set(True)
            else:
                return
        if not self._ask_missing_deps(self.deps, "full"):
            return
        media = self._select_media()
        if not media:
            return
        out_root = self._select_dir("选择转录与汇总保存目录")
        if not out_root:
            return
        excel = filedialog.asksaveasfilename(
            title="保存 Excel 汇总",
            initialfile="转录汇总.xlsx",
            initialdir=out_root,
            defaultextension=".xlsx",
            filetypes=[("Excel 表格", "*.xlsx")],
        )
        if not excel:
            return
        self._start_task(self._params("full", media, out_root, excel), out_root)

    def _start_task(self, params: TaskParams, context_path: str) -> None:
        if self.controller.running:
            messagebox.showwarning("任务进行中", "请先停止当前任务")
            return
        if self._download_busy:
            messagebox.showwarning("下载进行中", "请先完成或取消模型下载")
            return
        self._save_settings()
        self._last_context = {"output": context_path}
        self.progress_var.set(0)
        self.status_var.set("准备任务...")
        self.set_running(True)
        self.controller.start(params)

    def set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        stop_state = "normal" if running else "disabled"
        for button in (
            self.btn_full,
            self.btn_trans,
            self.btn_summary,
            self.btn_install,
            self.btn_clean,
            self.btn_download_model,
            self.btn_punct_download,
        ):
            button.configure(state=state)
        self.btn_stop.configure(state=stop_state)
        self.btn_cancel_download.configure(
            state="normal" if self._download_busy else "disabled"
        )

    def stop_task(self) -> None:
        self.controller.cancel(hard_after_seconds=2.0)
        self.status_var.set("正在停止...")

    def on_task_finished(self, outcome) -> None:
        self.set_running(False)
        output = self._last_context.get("output", "")
        if outcome.cancelled:
            self.progress_var.set(0)
            self.status_var.set("任务已取消")
            messagebox.showwarning("任务取消", outcome.message)
        elif outcome.ok:
            self.progress_var.set(100)
            self.status_var.set("任务完成")
            text = outcome.message
            if output:
                text += f"\n输出位置: {output}"
            messagebox.showinfo("任务完成", text)
        else:
            self.progress_var.set(0)
            self.status_var.set("任务失败")
            messagebox.showerror("任务失败", outcome.message or "未知错误，请查看日志")
        self.refresh_dependencies(defer_heavy=True)

    def install_missing_deps(self) -> None:
        missing = deps.missing_packages(self.deps, "full")
        if self.punct_var.get():
            if not self.deps.funasr:
                missing.append("funasr")
            if not self.deps.modelscope:
                missing.append("modelscope")
        if not missing:
            messagebox.showinfo("依赖检查", "常用依赖均已安装")
            return
        self.btn_install.configure(state="disabled")

        def worker() -> None:
            ok, output = deps.install_packages(missing)
            self.root.after(0, lambda: self._install_finished(ok, output))

        threading.Thread(target=worker, daemon=True).start()
        self.log("INFO", f"开始安装: {', '.join(missing)}")

    def _install_finished(self, ok: bool, output: str) -> None:
        self.btn_install.configure(state="normal")
        if ok:
            self.log("SUCCESS", "依赖安装完成")
        else:
            self.log("ERROR", f"依赖安装失败:\n{output}")
        self.refresh_dependencies(defer_heavy=True)

    def _download_button_state(self, busy: bool) -> None:
        self._download_busy = busy
        task_state = "disabled" if (busy or self._running) else "normal"
        self.btn_download_model.configure(state=task_state)
        self.btn_punct_download.configure(state=task_state)
        self.btn_cancel_download.configure(state="normal" if busy else "disabled")

    def _selected_download_size(self) -> str:
        label = self.download_label_var.get()
        for size, display in MODEL_LABELS:
            if display == label:
                return size
        return "base"

    def download_whisper_model(self) -> None:
        if self._download_busy:
            return
        if self._running:
            messagebox.showwarning("任务进行中", "转录任务运行时不能下载模型")
            return
        size = self._selected_download_size()
        target = paths.MODEL_DIR / f"{size}.pt"
        if target.exists():
            if not messagebox.askyesno("模型已存在", f"{target.name} 已存在，是否覆盖/续传？"):
                return
        paths.MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self._download_cancel.clear()
        self.download_progress_var.set(0)
        self._download_button_state(True)
        self.download_status_var.set("连接服务器...")

        def worker() -> None:
            try:
                urls = downloader.whisper_model_urls(size)
                last_error: Exception | None = None
                for url in urls:
                    if self._download_cancel.is_set():
                        break
                    try:
                        self._root_after(lambda: self.download_status_var.set(f"下载 {target.name}"))
                        downloader.download_file(
                            url,
                            target,
                            cancel=self._download_cancel,
                            progress=self._download_progress_callback,
                            retries=2,
                        )
                        last_error = None
                        break
                    except downloader.DownloadCancelled:
                        break
                    except downloader.DownloadError as exc:
                        last_error = exc
                        self._root_after(lambda: self.log("WARN", f"下载源失败，尝试下一镜像: {exc}"))
                if last_error is None and target.exists():
                    self._root_after(lambda: self.log("SUCCESS", f"{target.name} 下载完成"))
                    self._root_after(lambda: self.download_status_var.set("下载完成"))
                elif self._download_cancel.is_set():
                    self._root_after(lambda: self.download_status_var.set("下载已取消"))
                else:
                    self._root_after(lambda: self.log("ERROR", f"模型下载失败: {last_error}"))
                    self._root_after(lambda: self.download_status_var.set("下载失败"))
            except Exception as exc:
                self._root_after(lambda: self.log("ERROR", f"模型下载失败: {exc}"))
                self._root_after(lambda: self.download_status_var.set("下载失败"))
            finally:
                self._root_after(self._download_button_state, False)
                self._root_after(lambda: self.refresh_dependencies(defer_heavy=True))

        threading.Thread(target=worker, daemon=True).start()

    def _root_after(self, callback, *args) -> None:
        try:
            self.root.after(0, lambda: callback(*args))
        except tk.TclError:
            pass

    def _download_progress_callback(self, done: int, total: int | None) -> None:
        percent = 0.0
        if total:
            percent = min(100.0, done / total * 100)
        text = f"{done / 1024 / 1024:.1f} MB" + (f" / {total / 1024 / 1024:.1f} MB" if total else "")
        self._root_after(lambda: self.download_progress_var.set(percent))
        self._root_after(lambda: self.download_status_var.set(text))

    def cancel_download(self) -> None:
        self._download_cancel.set()
        self.download_status_var.set("正在取消...")

    def download_punctuation(self) -> None:
        if self._download_busy:
            return
        if self._running:
            messagebox.showwarning("任务进行中", "转录任务运行时不能下载模型")
            return
        target = paths.MODEL_DIR / "ct-punc"
        self._download_cancel.clear()
        self.download_progress_var.set(0)
        self.download_status_var.set("准备下载标点模型...")
        self._download_button_state(True)

        def worker() -> None:
            try:
                downloader.download_punctuation_model(
                    target,
                    cancel=self._download_cancel,
                    progress=self._download_progress_callback,
                )
                if target.is_dir():
                    self._root_after(lambda: self.log("SUCCESS", "ct-punc 标点模型下载完成"))
                    self._root_after(lambda: self.download_status_var.set("标点模型就绪"))
            except downloader.DownloadCancelled:
                self._root_after(lambda: self.download_status_var.set("下载已取消"))
            except Exception as exc:
                self._root_after(lambda: self.log("ERROR", f"标点模型下载失败: {exc}"))
                self._root_after(lambda: self.download_status_var.set("下载失败"))
            finally:
                self._root_after(self._download_button_state, False)
                self._root_after(lambda: self.refresh_dependencies(defer_heavy=True))

        threading.Thread(target=worker, daemon=True).start()

    def clean_model_cache(self) -> None:
        pt_files = sorted(paths.MODEL_DIR.glob("*.pt")) + sorted(paths.MODEL_DIR.glob("*.pt.part"))
        if not pt_files:
            messagebox.showinfo("清理", "没有可清理的 Whisper 模型文件")
            return
        if not messagebox.askyesno("确认清理", f"将删除 {len(pt_files)} 个模型文件，之后需要重新下载。"):
            return
        try:
            for path in pt_files:
                path.unlink(missing_ok=True)
            self.log("SUCCESS", "Whisper 模型缓存已清理")
        except OSError as exc:
            self.log("ERROR", f"清理模型失败: {exc}")

    def on_close(self) -> None:
        if self.controller.running and not messagebox.askyesno("确认退出", "任务仍在运行，关闭将强制中断，是否退出？"):
            return
        if self._download_busy:
            self._download_cancel.set()
        self.controller.shutdown()
        try:
            self.cfg.window_size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        except tk.TclError:
            pass
        self._save_settings()
        self.root.destroy()


def main() -> None:
    paths.ensure_dirs()
    logging_utils.setup_base_logging(paths.LOG_FILE)
    root = tk.Tk()
    app = WhisperApp(root)
    root.mainloop()

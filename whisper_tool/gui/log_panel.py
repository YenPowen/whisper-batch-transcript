# -*- coding: utf-8 -*-
"""支持搜索、复制与颜色分级的内嵌日志面板。"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import ttk


LEVEL_COLORS = {
    "INFO": "#334155",
    "SUCCESS": "#15803d",
    "WARN": "#b45309",
    "WARNING": "#b45309",
    "ERROR": "#dc2626",
}


class LogPanel(ttk.Frame):
    def __init__(self, master, title: str = "运行日志", max_lines: int = 5000) -> None:
        super().__init__(master, padding=(10, 4))
        self.max_lines = max_lines
        self._matches: list[str] = []
        self._match_index = -1
        self._last_keyword = ""

        header = ttk.Frame(self)
        header.pack(fill="x")
        ttk.Label(header, text=title).pack(side="left")
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(header, textvariable=self.search_var, width=24)
        search_entry.pack(side="left", padx=(12, 4))
        search_entry.bind("<Return>", lambda _event: self.search_next())
        ttk.Button(header, text="查找", width=6, command=self.search_next).pack(side="left", padx=2)
        ttk.Button(header, text="清空日志", width=9, command=self.clear).pack(side="right")
        ttk.Button(header, text="复制", width=5, command=self.copy_selection).pack(side="right", padx=2)

        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, pady=(4, 0))
        self.text = tk.Text(
            body,
            height=12,
            wrap="word",
            font=("Consolas", 9),
            bg="#0f172a",
            fg="#e2e8f0",
            insertbackground="#e2e8f0",
            relief="flat",
            padx=8,
            pady=6,
            state="disabled",
        )
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.tag_configure("search_hit", background="#facc15", foreground="#1e293b")
        for level, color in LEVEL_COLORS.items():
            self.text.tag_configure(level, foreground=color)
        self.text.bind("<Control-c>", lambda _event: self.copy_selection())
        self.text.bind("<Control-a>", lambda _event: self.select_all())

    def append(self, level: str, message: str) -> None:
        normalized = level.upper()
        if normalized == "SUCCESS":
            tag = "SUCCESS"
        elif normalized in LEVEL_COLORS:
            tag = normalized
        else:
            tag = "INFO"
        self.text.configure(state="normal")
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.text.insert(tk.END, f"[{stamp}] {message}\n", (tag,))
        lines = int(self.text.index("end-1c").split(".")[0])
        if lines > self.max_lines:
            self.text.delete("1.0", f"{lines - self.max_lines + 20}.0")
        self.text.see(tk.END)
        self.text.configure(state="disabled")

    def clear(self) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", tk.END)
        self.text.configure(state="disabled")
        self._matches = []
        self._match_index = -1

    def _selected_text(self) -> str:
        try:
            return self.text.get("sel.first", "sel.last")
        except tk.TclError:
            return ""

    def copy_selection(self) -> None:
        selected = self._selected_text()
        if selected:
            self.clipboard_clear()
            self.clipboard_append(selected)

    def select_all(self) -> None:
        self.text.configure(state="normal")
        self.text.tag_remove("sel", "1.0", tk.END)
        self.text.tag_add("sel", "1.0", "end-1c")
        self.text.configure(state="disabled")

    def search_next(self) -> None:
        keyword = self.search_var.get().strip()
        if not keyword:
            return
        if self._last_keyword != keyword:
            self._matches = []
            self._match_index = -1
            self._last_keyword = keyword
        if not self._matches:
            start = "1.0"
            while True:
                pos = self.text.search(keyword, start, stopindex=tk.END, nocase=True)
                if not pos:
                    break
                end = f"{pos}+{len(keyword)}c"
                self._matches.append((pos, end))
                start = end
        if not self._matches:
            return
        self._match_index = (self._match_index + 1) % len(self._matches)
        pos, end = self._matches[self._match_index]
        self.text.tag_remove("sel", "1.0", tk.END)
        self.text.tag_add("sel", pos, end)
        self.text.see(pos)

# -*- coding: utf-8 -*-
"""读取转录 TXT 并汇总为 Excel，依赖只在真正需要时导入。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from .events import DependencyMissingError


LOGGER = logging.getLogger(__name__)


def read_txt_file(path: Path) -> str:
    content = ""
    if not path.exists():
        return content
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            content = path.read_text(encoding=encoding)
            break
        except (UnicodeDecodeError, OSError):
            continue
    else:
        LOGGER.warning("无法读取 %s（编码不受支持）", path)
    return content.strip()


def summarize_to_excel(
    root_dir: Path,
    excel_path: Path,
    t2s: bool = True,
    progress_callback: Callable[[float], None] | None = None,
    cancel: object | None = None,
) -> bool:
    try:
        import pandas as pd
        from openpyxl import load_workbook
    except ImportError as exc:
        raise DependencyMissingError("汇总 Excel 需要 pandas 与 openpyxl") from exc

    txt_files = sorted(root_dir.rglob("*.txt"))
    rows: list[dict[str, str]] = []
    total = len(txt_files)
    for index, txt_path in enumerate(txt_files, start=1):
        if cancel is not None and getattr(cancel, "is_set", lambda: False)():
            LOGGER.warning("Excel 汇总已取消")
            return False
        text = read_txt_file(txt_path)
        if t2s:
            try:
                import opencc

                text = opencc.OpenCC("t2s").convert(text)
            except Exception:
                pass
        rows.append(
            {
                "视频/音频名称": txt_path.parent.name,
                "完整文本": text,
                "文本文件路径": str(txt_path.resolve()),
            }
        )
        if progress_callback:
            progress_callback(index / max(total, 1) * 100)
    if not rows:
        LOGGER.error("未找到任何 TXT 转录结果: %s", root_dir)
        return False

    excel_path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    try:
        frame.to_excel(excel_path, index=False, sheet_name="转录结果", engine="openpyxl")
        workbook = load_workbook(excel_path)
        sheet = workbook.active
        sheet.column_dimensions["A"].width = 35
        sheet.column_dimensions["B"].width = 110
        sheet.column_dimensions["C"].width = 60
        workbook.save(excel_path)
        LOGGER.info("Excel 汇总完成，共 %s 条记录: %s", len(rows), excel_path)
        return True
    except Exception:
        LOGGER.exception("保存 Excel 失败: %s", excel_path)
        return False

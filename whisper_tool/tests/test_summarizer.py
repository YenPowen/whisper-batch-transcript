# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from whisper_tool.core.summarizer import summarize_to_excel


class SummarizerTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            import pandas  # noqa: F401
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("pandas/openpyxl 未安装")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_summarizes_txt_recursively(self) -> None:
        root = Path(self.tmp.name)
        first = root / "video-one"
        second = root / "video-two"
        first.mkdir(parents=True)
        second.mkdir(parents=True)
        (first / "video-one.txt").write_text("第一段内容", encoding="utf-8")
        (second / "video-two.txt").write_text("第二段内容", encoding="utf-8")
        excel = root / "汇总.xlsx"
        ok = summarize_to_excel(root, excel, t2s=False)
        self.assertTrue(ok)
        import pandas as pd

        frame = pd.read_excel(excel)
        self.assertEqual(len(frame), 2)
        self.assertIn("第一段内容", frame["完整文本"].tolist())


if __name__ == "__main__":
    unittest.main()

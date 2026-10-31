# -*- coding: utf-8 -*-

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from whisper_tool.core.exporter import (
    ExportOptions,
    expected_files,
    write_transcription_outputs,
)
from whisper_tool.core.text import TextProcessor


class ExporterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_writes_all_requested_formats(self) -> None:
        root = Path(self.tmp.name)
        subdir = root / "sample"
        result = {
            "text": "你好世界",
            "segments": [
                {"id": 0, "start": 0.0, "end": 1.25, "text": "你好"},
                {"id": 1, "start": 1.25, "end": 2.0, "text": "世界"},
            ],
        }
        options = ExportOptions(out_txt=True, out_srt=True, out_json=True)
        files = write_transcription_outputs(
            "sample",
            subdir,
            result,
            options,
            TextProcessor(t2s=False),
        )
        self.assertEqual(len(files), 3)
        self.assertEqual((subdir / "sample.txt").read_text(encoding="utf-8"), "你好世界")
        srt = (subdir / "sample.srt").read_text(encoding="utf-8")
        self.assertIn("00:00:00,000 --> 00:00:01,250", srt)
        payload = json.loads((subdir / "sample.json").read_text(encoding="utf-8"))
        self.assertEqual(payload["segments"][1]["text"], "世界")

    def test_expected_files_handles_partial_formats(self) -> None:
        options = ExportOptions(out_txt=True, out_srt=False, out_json=True)
        files = expected_files("video", Path("out"), options)
        self.assertEqual([path.name for path in files], ["video.txt", "video.json"])


if __name__ == "__main__":
    unittest.main()

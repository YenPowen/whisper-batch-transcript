# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from whisper_tool.core.events import BatchResult, MediaConversionError
from whisper_tool.core.transcriber import TranscribeOptions, transcribe_batch


class FakeEngine:
    def transcribe(self, *_args, **_kwargs):
        return {
            "text": "hello world",
            "segments": [{"id": 0, "start": 0.0, "end": 1.0, "text": "hello world"}],
        }


class TranscriberTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _make_media(self, name: str) -> Path:
        media = Path(self.tmp.name) / name
        media.write_bytes(b"fake")
        return media

    def test_batch_writes_successfully(self) -> None:
        media = self._make_media("demo.mp4")
        output = Path(self.tmp.name) / "out"

        def fake_convert(_source, wav_path, cancel=None, ffmpeg=None, timeout_seconds=0):
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(b"wav")
            return wav_path

        with mock.patch("whisper_tool.core.transcriber.convert_to_wav", side_effect=fake_convert):
            result = transcribe_batch(
                [media],
                output,
                FakeEngine(),
                TranscribeOptions(t2s=False, out_json=False),
            )
        self.assertIsInstance(result, BatchResult)
        self.assertEqual(result.success, 1)
        self.assertEqual(result.failed, 0)
        txt = output / "demo" / "demo.txt"
        self.assertTrue(txt.exists())
        self.assertEqual(txt.read_text(encoding="utf-8"), "hello world")

    def test_same_stem_uses_separate_directories(self) -> None:
        media_a = self._make_media("same.mp4")
        media_b = self._make_media("same.mkv")

        def fake_convert(_source, wav_path, cancel=None, ffmpeg=None, timeout_seconds=0):
            wav_path.parent.mkdir(parents=True, exist_ok=True)
            wav_path.write_bytes(b"wav")
            return wav_path

        with mock.patch("whisper_tool.core.transcriber.convert_to_wav", side_effect=fake_convert):
            transcribe_batch(
                [media_a, media_b],
                Path(self.tmp.name) / "dup_out",
                FakeEngine(),
                TranscribeOptions(t2s=False, out_json=False),
            )
        dirs = sorted(path.name for path in (Path(self.tmp.name) / "dup_out").iterdir() if path.is_dir())
        self.assertEqual(dirs, ["same", "same_2"])

    def test_conversion_error_is_reported_per_file(self) -> None:
        media = self._make_media("broken.mp4")
        output = Path(self.tmp.name) / "err_out"
        with mock.patch(
            "whisper_tool.core.transcriber.convert_to_wav",
            side_effect=MediaConversionError("ffmpeg failed"),
        ):
            result = transcribe_batch(
                [media],
                output,
                FakeEngine(),
                TranscribeOptions(t2s=False),
            )
        self.assertEqual(result.failed, 1)
        self.assertEqual(result.success, 0)


if __name__ == "__main__":
    unittest.main()

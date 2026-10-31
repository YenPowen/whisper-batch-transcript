# -*- coding: utf-8 -*-

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from whisper_tool import config


class ConfigTests(unittest.TestCase):
    def test_save_and_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "config_v6.json"
            with mock.patch.object(config.paths, "CONFIG_FILE", target):
                source = config.AppConfig(
                    model_size="small",
                    language="en",
                    punctuation=True,
                    out_txt=False,
                    initial_prompt="Hello",
                )
                self.assertTrue(config.save_config(source))
                loaded = config.load_config()
                self.assertEqual(loaded.model_size, "small")
                self.assertEqual(loaded.language, "en")
                self.assertTrue(loaded.punctuation)
                self.assertFalse(loaded.out_txt)
                self.assertEqual(loaded.initial_prompt, "Hello")

    def test_legacy_json_is_migrated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            legacy = base / "config.json"
            legacy.write_text(
                '{"model_size":"large-v3-turbo","lang":"zh","out_json":true,"version":1}',
                encoding="utf-8",
            )
            with (
                mock.patch.object(config.paths, "CONFIG_FILE", base / "config_v6.json"),
                mock.patch.object(config.paths, "LEGACY_CONFIG_FILE", legacy),
            ):
                loaded = config.load_config()
                self.assertEqual(loaded.model_size, "large-v3-turbo")
                self.assertEqual(loaded.language, "zh")
                self.assertTrue(loaded.out_json)


if __name__ == "__main__":
    unittest.main()

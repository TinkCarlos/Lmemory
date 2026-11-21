"""Tests for the generic Antigravity hook adapter under extras/antigravity."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
ADAPTER_PATH = REPO / "extras" / "antigravity" / "lmemory-agy.py"


def _load_adapter():
    spec = importlib.util.spec_from_file_location("lmemory_agy_extra", ADAPTER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class TestAntigravityHook(unittest.TestCase):
    def test_no_personal_paths_hardcoded(self):
        text = ADAPTER_PATH.read_text(encoding="utf-8")
        self.assertNotIn("/Users/", text)
        self.assertNotIn("第二大脑", text)

    def test_latest_step_key_widens_across_long_turn(self):
        mod = _load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "transcript.jsonl"
            filler = "x" * 4000
            rows = [{"step_index": 1, "type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "start"}]
            for idx in range(2, 400):
                rows.append({"step_index": idx, "type": "GENERIC", "content": filler})
            tpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            self.assertGreater(tpath.stat().st_size, 512_000)

            self.assertEqual(mod._latest_step_key({"transcriptPath": str(tpath)}), "step:1")
            self.assertIsNone(mod._latest_step_key({"transcriptPath": str(Path(tmp) / "missing.jsonl")}))

    def test_cmd_prompt_skips_machine_and_duplicate_turns(self):
        mod = _load_adapter()
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(mod, "STATE_ROOT", Path(tmp)):
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = mod.cmd_prompt({"lastUserInput": "[plan review due]"})
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()), {})

            payload = {"conversationId": "c-1", "initialNumSteps": 2, "lastUserInput": ""}
            self.assertTrue(mod._dedupe_turn("lmemory", "c-1", payload))
            self.assertFalse(mod._dedupe_turn("lmemory", "c-1", payload))


if __name__ == "__main__":
    unittest.main()

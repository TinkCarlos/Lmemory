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

    def test_extract_user_text_unwraps_t3_harness_and_preserves_literal_tags(self):
        mod = _load_adapter()
        wrapped = (
            "<USER_REQUEST>\n"
            "<t3_code_instructions>\n## T3 Code interaction mode: Default\n</t3_code_instructions>\n\n"
            "<user_request>\n帮我查一下上次决定的发布策略\n</user_request>"
            "<runtime_info>T3 Code</runtime_info>\n"
            "</USER_REQUEST>\n"
            "<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-23T15:48:00+08:00.\n</ADDITIONAL_METADATA>"
        )
        self.assertEqual(mod._extract_user_text(wrapped), "帮我查一下上次决定的发布策略")

        literal = "<USER_REQUEST>\n帮我解释 <user_request>foo</user_request> 标签\n</USER_REQUEST>"
        self.assertEqual(mod._extract_user_text(literal), "帮我解释 <user_request>foo</user_request> 标签")

        # Outer timestamp changes must produce the same turn key
        wrapped2 = wrapped.replace("15:48:00", "15:48:09")
        self.assertEqual(
            mod._turn_keys({"initialNumSteps": 1, "lastUserInput": wrapped})["initKey"],
            mod._turn_keys({"initialNumSteps": 1, "lastUserInput": wrapped2})["initKey"],
        )

        # Transcript turn reader must store clean user prompt, not T3 instructions
        with tempfile.TemporaryDirectory() as tmp:
            tpath = Path(tmp) / "transcript.jsonl"
            rows = [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "content": wrapped},
                {"step_index": 1, "type": "PLANNER_RESPONSE", "content": "已查到上次发布策略。"},
            ]
            tpath.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
            turns = mod._read_antigravity_turns(tpath)
            self.assertEqual(len(turns), 1)
            self.assertEqual(turns[0]["ask"], "帮我查一下上次决定的发布策略")
            self.assertEqual(turns[0]["answer"], "已查到上次发布策略。")


if __name__ == "__main__":
    unittest.main()

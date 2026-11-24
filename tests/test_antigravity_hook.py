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

    def test_compaction_checkpoint_rehydrates_and_resets_recall_across_multiple_compactions(self):
        import shutil
        import subprocess
        import sys

        mod = _load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "vault"
            shutil.copytree(REPO / "template", vault)
            (vault / "团队手册").mkdir(parents=True, exist_ok=True)
            (vault / "团队手册/测试环境.md").write_text(
                "---\ntitle: 测试环境\nstatus: active\n---\n\n# 测试环境\n\n测试环境每天凌晨 3 点自动重置数据；需要保留的数据要提前申请快照。\n",
                encoding="utf-8",
            )
            (vault / "90 系统文件").mkdir(parents=True, exist_ok=True)
            (vault / "90 系统文件/canonical_sources.psv").write_text(
                "Z22|测试环境|团队手册/测试环境.md|测试环境每天凌晨 3 点重置数据；要保留先申请快照\n",
                encoding="utf-8",
            )
            work = root / "work" / "proj"
            work.mkdir(parents=True)
            state = root / "state"
            state.mkdir()
            (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
            env = {
                **os.environ,
                "OBSIDIAN_VAULT": str(vault),
                "LMEMORY_STATE_DIR": str(state),
                "LMEMORY_CACHE_DIR": str(root / "cache"),
                "LMEMORY_NO_QUERY_LOG": "1",
                "LMEMORY_RECALL_PROMPT": "1",
            }
            subprocess.run(
                [sys.executable, str(REPO / "skill/lmemory/scripts/recall_index.py"), "--vault", str(vault), "--stats"],
                env=env,
                capture_output=True,
                check=True,
                timeout=60,
            )

            tpath = root / "transcript.jsonl"
            rows = [
                {"step_index": 0, "type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "测试环境的数据怎么保留"},
            ]
            tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")

            def call_cmd(fn, payload):
                buf = io.StringIO()
                with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(mod, "STATE_ROOT", root / "hook-state"):
                    with redirect_stdout(buf):
                        fn(payload)
                return json.loads(buf.getvalue())

            # Turn 1: recalls 测试环境
            res1 = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 1,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:00:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            txt1 = "\n".join(s["systemMessage"]["systemMessage"] for s in res1.get("injectSteps", []))
            self.assertIn("团队手册/测试环境.md", txt1)

            # Same turn continuation (subagent wakeup with same outerMeta) must be deduped
            res_same = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 20,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:00:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            self.assertEqual(res_same, {})

            # Turn 2 before compaction: already recalled in this session -> suppressed
            rows.append({"step_index": 25, "type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "测试环境的数据怎么保留"})
            tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            res2 = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 26,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:05:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            self.assertEqual(res2, {})

            # Compaction #1 mid-turn (CHECKPOINT at step 30): must re-hydrate start_text AND reset recall
            rows.append({"step_index": 30, "type": "CHECKPOINT", "content": "# Resuming from a compaction"})
            tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            res_cmp1 = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 31,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:05:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            txt_cmp1 = "\n".join(s["systemMessage"]["systemMessage"] for s in res_cmp1.get("injectSteps", []))
            self.assertIn("lmemory_", txt_cmp1)

            # Next step after Compaction #1 must NOT double re-hydrate
            res_cmp1_dup = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 32,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:05:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            self.assertEqual(res_cmp1_dup, {})

            # Turn 3 after Compaction #1: 测试环境 can be recalled again!
            rows.append({"step_index": 40, "type": "USER_INPUT", "source": "USER_EXPLICIT", "content": "测试环境的数据怎么保留"})
            tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            res3 = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 41,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:10:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            txt3 = "\n".join(s["systemMessage"]["systemMessage"] for s in res3.get("injectSteps", []))
            self.assertIn("团队手册/测试环境.md", txt3)

            # Compaction #2 (CHECKPOINT at step 60): re-hydrates again once
            rows.append({"step_index": 60, "type": "CHECKPOINT", "content": "# Resuming from a compaction"})
            tpath.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
            res_cmp2 = call_cmd(mod.cmd_prompt, {
                "conversationId": "conv-cmp",
                "transcriptPath": str(tpath),
                "cwd": str(work),
                "initialNumSteps": 61,
                "lastUserInput": "<USER_REQUEST>\n测试环境的数据怎么保留\n</USER_REQUEST>\n<ADDITIONAL_METADATA>\nThe current local time is: 2026-11-24T10:10:00+08:00.\n</ADDITIONAL_METADATA>",
            })
            txt_cmp2 = "\n".join(s["systemMessage"]["systemMessage"] for s in res_cmp2.get("injectSteps", []))
            self.assertIn("lmemory_", txt_cmp2)

    def test_cmd_stop_uses_recollect_state_dir(self):
        mod = _load_adapter()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            state = root / "state"
            state.mkdir()
            (state / "import.json").write_text(json.dumps({"consent": True}), encoding="utf-8")
            tpath = root / "transcript.jsonl"
            tpath.write_text('{"step_index": 0, "type": "USER_INPUT", "content": "hi"}\n', encoding="utf-8")
            buf = io.StringIO()
            with (
                mock.patch.dict(os.environ, {"LMEMORY_STATE_DIR": str(state)}, clear=False),
                mock.patch.object(mod.subprocess, "Popen") as popen,
                redirect_stdout(buf),
            ):
                rc = mod.cmd_stop({"transcriptPath": str(tpath), "conversationId": "c-stop", "cwd": str(root)})
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(buf.getvalue()), {})
            self.assertTrue(popen.called)


if __name__ == "__main__":
    unittest.main()

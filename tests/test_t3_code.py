"""Tests for T3 Code support across Lmemory redaction, capture, session import, doctor, and T3 installer."""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skill" / "lmemory" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(REPO / "sdk") not in sys.path:
    sys.path.insert(0, str(REPO / "sdk"))

import import_sessions  # noqa: E402
import lmemory_capture  # noqa: E402
import lmemory_redact  # noqa: E402
from lmemory import doctor  # noqa: E402


def _load_install_t3():
    path = REPO / "extras" / "antigravity" / "install_t3.py"
    spec = importlib.util.spec_from_file_location("lmemory_install_t3", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


T3_WRAPPED = (
    "<t3_code_instructions>\n"
    "## T3 Code interaction mode: Default\n"
    "Prefer making reasonable assumptions.\n"
    "</t3_code_instructions>\n\n"
    "<user_request>\n"
    "以后一律用 pnpm，不要再用 npm 了\n"
    "</user_request>"
    "<runtime_info>Running in T3 Code</runtime_info>"
)


class TestT3CodeSupport(unittest.TestCase):
    def test_human_words_and_own_words_preserve_t3_user_request(self):
        unwrapped = lmemory_redact.human_words(T3_WRAPPED)
        self.assertEqual(unwrapped, "以后一律用 pnpm，不要再用 npm 了")
        # Previously own_words() stripped <user_request>...</user_request> to empty!
        self.assertEqual(lmemory_capture.own_words(unwrapped), "以后一律用 pnpm，不要再用 npm 了")
        self.assertTrue(lmemory_capture.correction_cue(lmemory_capture.own_words(unwrapped)))

        # Literal <user_request> inside normal prose must stay intact
        literal = "帮我解释 <user_request>foo</user_request> 这个标签的用途"
        self.assertEqual(lmemory_redact.human_words(literal), literal)

    def test_import_sessions_unwraps_t3_claude_and_codex_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            claude_log = Path(tmp) / "claude-session.jsonl"
            claude_rows = [
                {"type": "user", "timestamp": "2026-11-23T07:00:00Z", "cwd": tmp,
                 "message": {"role": "user", "content": T3_WRAPPED}},
                {"type": "assistant", "timestamp": "2026-11-23T07:00:05Z",
                 "message": {"role": "assistant", "content": [{"type": "text", "text": "好的，后续都用 pnpm。"}]}},
            ]
            claude_log.write_text("\n".join(json.dumps(r) for r in claude_rows) + "\n", encoding="utf-8")
            parsed_claude = import_sessions.read_claude(claude_log)
            self.assertEqual(len(parsed_claude["turns"]), 1)
            self.assertEqual(parsed_claude["turns"][0]["ask"], "以后一律用 pnpm，不要再用 npm 了")

            codex_log = Path(tmp) / "rollout-t3.jsonl"
            codex_rows = [
                {"type": "session_meta", "timestamp": "2026-11-23T07:00:00Z", "payload": {"id": "s-1", "cwd": tmp}},
                {"type": "response_item", "timestamp": "2026-11-23T07:00:01Z",
                 "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": T3_WRAPPED}]}},
                {"type": "response_item", "timestamp": "2026-11-23T07:00:05Z",
                 "payload": {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "记住了，改用 pnpm。"}]}},
            ]
            codex_log.write_text("\n".join(json.dumps(r) for r in codex_rows) + "\n", encoding="utf-8")
            parsed_codex = import_sessions.read_codex(codex_log)
            self.assertEqual(len(parsed_codex["turns"]), 1)
            self.assertEqual(parsed_codex["turns"][0]["ask"], "以后一律用 pnpm，不要再用 npm 了")

    def test_install_t3_and_doctor_detection(self):
        mod = _load_install_t3()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            t3_dir = root / ".t3"
            cfg = t3_dir / "userdata" / "providers" / "antigravity" / "abc123" / "config"
            (cfg / "skills").mkdir(parents=True)
            # Pre-existing unrelated hook and MCP server must be preserved
            (cfg / "hooks.json").write_text(json.dumps({"prompt-optimizer": {"PreInvocation": []}}), encoding="utf-8")
            (cfg / "mcp_config.json").write_text(json.dumps({"mcpServers": {"other": {"command": "other"}}}), encoding="utf-8")
            hook_dest = root / "hooks" / "lmemory-agy.py"

            # Dry run changes nothing
            rc = mod.main([
                "--t3-dir", str(t3_dir),
                "--vault", str(root / "vault"),
                "--lmemory-bin", "/opt/bin/lmemory",
                "--python", "/opt/bin/python3",
                "--hook-path", str(hook_dest),
                "--dry-run",
            ])
            self.assertEqual(rc, 0)
            self.assertFalse(hook_dest.exists())
            self.assertNotIn("lmemory", json.loads((cfg / "hooks.json").read_text(encoding="utf-8")))

            # Real install merges cleanly without dropping existing entries
            rc = mod.main([
                "--t3-dir", str(t3_dir),
                "--vault", str(root / "vault"),
                "--lmemory-bin", "/opt/bin/lmemory",
                "--python", "/opt/bin/python3",
                "--hook-path", str(hook_dest),
                "--state-dir", str(root / "state"),
            ])
            self.assertEqual(rc, 0)
            self.assertTrue(hook_dest.is_file())
            hooks_data = json.loads((cfg / "hooks.json").read_text(encoding="utf-8"))
            self.assertIn("prompt-optimizer", hooks_data)
            self.assertIn("lmemory", hooks_data)
            mcp_data = json.loads((cfg / "mcp_config.json").read_text(encoding="utf-8"))
            self.assertIn("other", mcp_data["mcpServers"])
            self.assertEqual(mcp_data["mcpServers"]["lmemory"]["command"], "/opt/bin/lmemory")
            self.assertTrue((cfg / "skills" / "lmemory" / "SKILL.md").is_file())

            # Doctor detects T3 Code Antigravity MCP
            with mock.patch.dict("os.environ", {"T3_DATA_DIR": str(t3_dir)}), mock.patch.object(Path, "home", return_value=root):
                apps = doctor._apps()
                self.assertIn("T3 Code (Antigravity MCP)", apps)

            # Uninstall removes only lmemory, leaving prompt-optimizer and other MCP intact
            rc = mod.main(["--t3-dir", str(t3_dir), "--uninstall"])
            self.assertEqual(rc, 0)
            hooks_after = json.loads((cfg / "hooks.json").read_text(encoding="utf-8"))
            self.assertIn("prompt-optimizer", hooks_after)
            self.assertNotIn("lmemory", hooks_after)
            mcp_after = json.loads((cfg / "mcp_config.json").read_text(encoding="utf-8"))
            self.assertIn("other", mcp_after["mcpServers"])
            self.assertNotIn("lmemory", mcp_after["mcpServers"])


if __name__ == "__main__":
    unittest.main()

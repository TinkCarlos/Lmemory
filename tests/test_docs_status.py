"""Every entry file an agent may read on its own carries the same, current status block (scripts/sync_status.py)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_status_block_is_in_sync_everywhere():
    res = subprocess.run([sys.executable, str(ROOT / "scripts/sync_status.py"), "--check"], capture_output=True,
                         text=True, timeout=60)
    assert res.returncode == 0, res.stdout + res.stderr + " — edit docs/STATUS*.md, then run scripts/sync_status.py"


def _status_texts() -> dict[str, str]:
    return {lang: (ROOT / f"docs/STATUS{lang}.md").read_text(encoding="utf-8") for lang in ("", ".zh")}


def test_source_status_links_to_current_comparison_and_attributes_upstream():
    version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
    for lang, text in _status_texts().items():
        assert "Lmemory" in text and "Tink" in text
        assert f"/releases/tag/v{version}" in text
        assert f"/blob/v{version}/README{lang}.md" in text
        assert f"NUMBERS{lang}.md" in text

        history = (ROOT / f"docs/NUMBERS{lang}.md").read_text(encoding="utf-8")
        assert "KRouter" in history and f"../README{lang}.md" in history

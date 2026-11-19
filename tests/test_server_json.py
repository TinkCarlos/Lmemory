"""Source checkout metadata uses the Lmemory identity and does not advertise unpublished assets."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_server_json_matches_the_package_and_the_readme_marker():
    server = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    version = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert server["name"] == "io.github.tinkcarlos/lmemory"
    assert server["title"] == "Lmemory"
    assert server["version"] == version
    assert server["repository"]["url"] == "https://github.com/TinkCarlos/Lmemory"
    assert 1 <= len(server["description"]) <= 100
    assert not server.get("packages") and not server.get("remotes")
    assert f"mcp-name: {server['name']}" in (ROOT / "README.md").read_text(encoding="utf-8")

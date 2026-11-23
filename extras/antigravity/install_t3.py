#!/usr/bin/env python3
"""Connect Lmemory (MCP + Antigravity lifecycle hooks + SKILL.md) to T3 Code's Antigravity provider configs.

T3 Code isolates Antigravity provider settings under `~/.t3/userdata/providers/antigravity/<hash>/config/`.
Other T3 Code providers (Claude Code, Codex, Cursor) automatically inherit their native host configs.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ADAPTER_SRC = HERE / "lmemory-agy.py"
SKILL_SRC = REPO / "plugin" / "skills" / "lmemory" / "SKILL.md"


def discover_t3_antigravity_configs(t3_dir: Path | None = None) -> list[Path]:
    root = (t3_dir or Path(os.environ.get("T3_DATA_DIR") or Path.home() / ".t3")) / "userdata" / "providers" / "antigravity"
    if not root.is_dir():
        return []
    return sorted(p for p in root.glob("*/config") if p.is_dir())


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write_json_atomic(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _default_lmemory_bin() -> str:
    local = Path.home() / ".local" / "bin" / "lmemory"
    if local.exists():
        return str(local)
    found = shutil.which("lmemory")
    return found or str(local)


def _default_python_bin() -> str:
    uv_py = Path.home() / ".local" / "share" / "uv" / "tools" / "lmemory" / "bin" / "python"
    if uv_py.exists():
        return str(uv_py)
    return sys.executable


def _default_vault() -> str:
    for env_key in ("LMEMORY_VAULT", "OBSIDIAN_VAULT"):
        val = os.environ.get(env_key, "").strip()
        if val:
            return str(Path(val).expanduser())
    vf = Path(os.environ.get("LMEMORY_VAULT_FILE") or Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "lmemory" / "vault")
    try:
        first = vf.read_text(encoding="utf-8").splitlines()[0].strip()
        if first:
            return str(Path(first).expanduser())
    except (OSError, IndexError):
        pass
    return ""


def _hook_entry(py_bin: str, hook_path: Path) -> dict:
    cmd_base = f"{py_bin} {hook_path}"
    return {
        "SessionStart": [{"type": "command", "command": f"{cmd_base} start", "timeout": 10}],
        "PreInvocation": [{"type": "command", "command": f"{cmd_base} prompt", "timeout": 10}],
        "Stop": [{"type": "command", "command": f"{cmd_base} stop", "timeout": 5}],
    }


def _mcp_entry(lmemory_bin: str, vault: str, state_dir: str) -> dict:
    args = ["--vault", vault, "mcp"] if vault else ["mcp"]
    entry: dict = {"command": lmemory_bin, "args": args}
    if state_dir:
        entry["env"] = {"LMEMORY_STATE_DIR": state_dir}
    return entry


def install_into_config(
    cfg_dir: Path,
    *,
    lmemory_bin: str,
    py_bin: str,
    hook_path: Path,
    vault: str,
    state_dir: str,
    install_mcp: bool = True,
    install_hooks: bool = True,
    install_skill: bool = True,
    dry_run: bool = False,
) -> dict:
    actions: list[str] = []

    if install_mcp:
        mcp_file = cfg_dir / "mcp_config.json"
        data = _read_json(mcp_file)
        servers = data.get("mcpServers")
        if servers is None:
            servers = {}
        if not isinstance(servers, dict):
            raise ValueError(f"{mcp_file}: mcpServers must be an object")
        entry = _mcp_entry(lmemory_bin, vault, state_dir)
        if servers.get("lmemory") != entry:
            actions.append(f"mcp:{mcp_file}")
            if not dry_run:
                servers["lmemory"] = entry
                data["mcpServers"] = servers
                _write_json_atomic(mcp_file, data)

    if install_hooks:
        if ADAPTER_SRC.is_file() and not hook_path.exists():
            actions.append(f"copy-hook:{hook_path}")
            if not dry_run:
                hook_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ADAPTER_SRC, hook_path)
                hook_path.chmod(0o755)
        hooks_file = cfg_dir / "hooks.json"
        data = _read_json(hooks_file)
        entry = _hook_entry(py_bin, hook_path)
        if data.get("lmemory") != entry:
            actions.append(f"hooks:{hooks_file}")
            if not dry_run:
                data["lmemory"] = entry
                _write_json_atomic(hooks_file, data)

    if install_skill and SKILL_SRC.is_file():
        skills_dir = cfg_dir / "skills"
        if skills_dir.exists() or skills_dir.is_symlink():
            target = skills_dir / "lmemory" / "SKILL.md"
            src_bytes = SKILL_SRC.read_bytes()
            if not target.is_file() or target.read_bytes() != src_bytes:
                actions.append(f"skill:{target}")
                if not dry_run:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(src_bytes)

    return {"config": str(cfg_dir), "actions": actions}


def uninstall_from_config(cfg_dir: Path, *, dry_run: bool = False) -> dict:
    actions: list[str] = []

    mcp_file = cfg_dir / "mcp_config.json"
    if mcp_file.is_file():
        data = _read_json(mcp_file)
        servers = data.get("mcpServers")
        if isinstance(servers, dict) and "lmemory" in servers:
            actions.append(f"remove-mcp:{mcp_file}")
            if not dry_run:
                servers.pop("lmemory", None)
                _write_json_atomic(mcp_file, data)

    hooks_file = cfg_dir / "hooks.json"
    if hooks_file.is_file():
        data = _read_json(hooks_file)
        if "lmemory" in data:
            actions.append(f"remove-hooks:{hooks_file}")
            if not dry_run:
                data.pop("lmemory", None)
                _write_json_atomic(hooks_file, data)

    return {"config": str(cfg_dir), "actions": actions}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Configure Lmemory MCP + hooks for T3 Code's Antigravity provider.")
    ap.add_argument("--t3-dir", default="", help="T3 Code data directory (default: $T3_DATA_DIR or ~/.t3)")
    ap.add_argument("--vault", default="", help="Path to Markdown memory vault (default: auto-detected)")
    ap.add_argument("--lmemory-bin", default="", help="Path to lmemory executable")
    ap.add_argument("--python", default="", help="Path to Python interpreter inside the Lmemory install")
    ap.add_argument("--hook-path", default="", help="Installed lmemory-agy.py path (default: ~/.gemini/config/hooks/lmemory-agy.py)")
    ap.add_argument("--state-dir", default="", help="Optional LMEMORY_STATE_DIR env for MCP server")
    ap.add_argument("--skip-mcp", action="store_true", help="Do not touch mcp_config.json")
    ap.add_argument("--skip-hooks", action="store_true", help="Do not touch hooks.json")
    ap.add_argument("--skip-skill", action="store_true", help="Do not copy lmemory SKILL.md")
    ap.add_argument("--uninstall", action="store_true", help="Remove lmemory entries from T3 Antigravity configs")
    ap.add_argument("--dry-run", action="store_true", help="Print planned changes without writing files")
    args = ap.parse_args(argv)

    t3_dir = Path(args.t3_dir).expanduser() if args.t3_dir else None
    configs = discover_t3_antigravity_configs(t3_dir)
    if not configs:
        print("No T3 Code Antigravity provider config directories found.")
        return 0

    results = []
    if args.uninstall:
        for cfg in configs:
            results.append(uninstall_from_config(cfg, dry_run=args.dry_run))
    else:
        lmemory_bin = args.lmemory_bin or _default_lmemory_bin()
        py_bin = args.python or _default_python_bin()
        hook_path = Path(args.hook_path).expanduser() if args.hook_path else (Path.home() / ".gemini" / "config" / "hooks" / "lmemory-agy.py")
        vault = str(Path(args.vault).expanduser()) if args.vault else _default_vault()
        state_dir = args.state_dir or os.environ.get("LMEMORY_STATE_DIR", "")
        for cfg in configs:
            results.append(
                install_into_config(
                    cfg,
                    lmemory_bin=lmemory_bin,
                    py_bin=py_bin,
                    hook_path=hook_path,
                    vault=vault,
                    state_dir=state_dir,
                    install_mcp=not args.skip_mcp,
                    install_hooks=not args.skip_hooks,
                    install_skill=not args.skip_skill,
                    dry_run=args.dry_run,
                )
            )

    print(json.dumps({"dryRun": args.dry_run, "configs": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

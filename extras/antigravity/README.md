# Optional Antigravity hook

Default `install.sh` does not enable this.

`lmemory-agy.py` bridges Antigravity lifecycle hooks (`SessionStart`, `PreInvocation`, `Stop`) to Lmemory:

- `SessionStart`: injects session startup context from your configured vault.
- `PreInvocation`: captures correction candidates, recalls relevant notes, and deduplicates mid-turn wakeups across long agent turns (widening transcript tail reads from 512 KB up to 16 MB).
- `Stop`: imports the finished session transcript in the background.

## Setup

1. Copy `lmemory-agy.py` to `~/.gemini/config/hooks/lmemory-agy.py` (or another writable path) and `chmod +x` it.
2. Add the entries from `hooks.json.example` to `~/.gemini/config/hooks.json`, replacing `/path/to/lmemory/bin/python` with the Python interpreter from your Lmemory install (for `uv tool install`, typically `~/.local/share/uv/tools/lmemory/bin/python`).
3. Ensure Lmemory knows your vault (via `OBSIDIAN_VAULT` or Lmemory's saved state / `vault.txt`).

Optional environment variables:

- `AGY_HOOK_STATE_DIR`: overrides hook turn-dedupe state directory (defaults to `~/.gemini/config/hooks/state`).
- `LMEMORY_STATE_DIR` / `OBSIDIAN_VAULT`: standard Lmemory overrides.
- `LMEMORY_INJECT=0`: disables `SessionStart` injection.

## T3 Code (Antigravity provider)

T3 Code stores Antigravity provider settings in isolated directories under `~/.t3/userdata/providers/antigravity/<id>/config/`. Its `skills` folder is normally symlinked to `~/.gemini/config/skills`, while `mcp_config.json` and `hooks.json` are separate.

`lmemory-agy.py` automatically unwraps T3 Code's `<t3_code_instructions>` / `<user_request>` / `<runtime_info>` wrapper so recall, correction capture, and session import see only the user's actual message.

Use the helper script to merge Lmemory's MCP server, hooks, and `SKILL.md` into every T3 Code Antigravity provider directory without overwriting other entries:

```bash
python3 extras/antigravity/install_t3.py --dry-run
python3 extras/antigravity/install_t3.py --vault "/absolute/path/to/your/vault"
```

Remove the T3 Code entries cleanly with:

```bash
python3 extras/antigravity/install_t3.py --uninstall
```

Other T3 Code providers (Claude Code, Codex, Cursor) reuse their native host configs automatically; `lmemory_redact.human_words()` also unwraps T3 Code prompt wrappers for their hooks and session imports.

# Lmemory

This directory is the **DeepSeek Harness socket** of Lmemory, not a second product.

The product is the repo root: router (`skill/lmemory`) + writer (`extras/host-daily-evolution`) + this socket. One vault. `dsh plugin add` does not start the timer.

Uninstalling the socket does not delete notes.

## Local test (before `dsh plugin add`)

```bash
node extras/dsh/test-bridge.mjs
./scripts/first_run.sh
```

## Install the product (repo root)

Skill + writer timer (needs `OBSIDIAN_VAULT` at **your** vault, not the clone template):

```bash
export OBSIDIAN_VAULT=/path/to/YourVault
./scripts/install.sh
```

Then, from a machine that already runs DSH. Prefer a spare profile. Point `dsh plugin add` at **this repo root**, not `extras/dsh`:

```bash
dsh plugin --profile web add github:TinkCarlos/Lmemory
# or, from a local clone:
dsh plugin add /absolute/path/to/Lmemory
```

Do not treat `extras/dsh` as a separate project to publish.

Tools: `lmemory_status` (includes `host_action` when the vault-page key and CLI login are missing — tell the host), `lmemory_preference`, `lmemory_correction`, `lmemory_memory`, `lmemory_project`, `lmemory_search`, `lmemory_suggest`.

If `canonical_match` is true, open `canonical_source`. Suggestions are hints, not hits. If `host_prompt` is present, ask the host; do not guess. On Windows the socket prefers `route_knowledge.py`.

The alias map is not writable from these tools. Mutate it with `maintain_aliases.py` after `acquire`.

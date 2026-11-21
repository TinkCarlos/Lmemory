# Protocol

<!-- lmemory-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Lmemory v2.1.3 (2026-11-21).** Maintained by [Tink](https://github.com/TinkCarlos). See the [release notes](https://github.com/TinkCarlos/Lmemory/releases/tag/v2.1.3) and the [bilingual ranking comparison](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/docs/BENCHMARK.md#bilingual-ranking-2026-11-21). Historical upstream measurements are labeled in [NUMBERS.md](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/docs/NUMBERS.md). [Installation](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/README.md).
<!-- lmemory-status:end -->

> Historical benchmark and client records on this page come from upstream. The README specifies the Lmemory build and its verification.

This is an **Agent knowledge OS**, not a search plugin.

- **Self-evolution** is the product (seal → distill → two-step promotion). Timer: the one-line install **asks before installing it** (no terminal, no timer); the manual `install.sh` from a clone installs it (`LMEMORY_NO_TIMER=1` skips). **API key first:** lock that provider's flagship model and run distill + promotion. **No key:** the user's own Claudian-class CLI subscription (`grok` / official Codex / `claude` / …) does the same work. `lamp: unused` = you turned the timer off.
- **Promotion is two-step:** five gates pass → write `provisional` the **same day**, no ask. Next similar task → **ask** (matcher in `skill/lmemory/scripts/ask_product.py`; at most one). Host adopts → `record`. This task accepted → `promote` writes `active`. Do not write `active` on `record`.
- **Correction-first:** current instruction and latest `supersedes` beat old logs.
- **Retrieval refuses rather than guesses:** ranked lexical recall over every page (words and Chinese character pairs, rule pages first), with an optional alias lock in front for fixed short nouns; a dual SHA-256 receipt; `recall: none` when nothing covers the question. No vector store by default. Citing a neighbour page as the answer is a protocol violation.

Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

1. Five zones: `01 项目` in progress; `02 经验与方法` verified reusable methods; `03 资料与证据` inputs and evidence; `04 已完成与复盘` finished results; `05 时间日志` what happened that day.
2. Four maturity layers: full logs → distillation → promotion → retrieval. Formal `02` requires the two-step gates above. Candidates stay in projects or materials until the five gates pass.
3. On conflict: the current user instruction and the latest `supersedes` beat old logs.
4. Clippings originals are copied only. Do not move them.
5. Routing uses an exact registered alias as a shortcut only when its anchor appears in a live source. A uniquely verified dated reply also counts as direct evidence. On an unverified alias or a question with further details, rank the notes in scope and offer partial aliases as hints. A complete uppercase identifier in the question must occur in a candidate source. Ranked matches are related evidence candidates, even at high lexical confidence. Quote a line that answers the question before using it. Say the memory has nothing on the question when no source supports it. A one-page route can widen to the vault and report `scope_widened`. Tied shortcuts across different pages are ambiguous and can produce a `host_prompt`. A replaced or expired page cannot lock. See [retrieval architecture](docs/ARCHITECTURE.md#l4-retrieval).
6. Every route prints a receipt: time, source path, source SHA-256, map SHA-256.
7. Two lanes, same job (distill + two-step promotion). **API key first:** keys live in `~/.dsh-lmemory-keys.env`, never in the vault (a key pasted on `90 系统文件/自动化/自进化钥匙.md` is moved there on the next run); lock the provider's flagship model (`/models` catalog; skip mini/haiku), run `api_writer.py`. **No key:** spawn a logged-in Claudian-class CLI (`grok`, official Codex, `claude`, cursor-agent, opencode, kimi, pi, vibe, antigravity) with that harness's flagship. The nightly steps use the same lane: same provider table, same flagship lock, same CLI list (`llm.py`). Do not use a PATH-level `agent`. Chat/IDE login is not a spawnable harness. No extra env file. Mounted agents must run `status` and tell the host if `host_action` is present. Do not print secrets. Do not commit a live key.
8. **One product: Lmemory.** Cursor, Codex, Claude Code, and DeepSeek Harness are sockets on one vault. Sharing is the vault and the alias map, not a second protocol. `extras/dsh` is the DSH socket (read-only tools). `extras/host-daily-evolution` is the writer. They are not two projects. Uninstalling the DSH socket does not delete notes. `dsh plugin add` does not start the timer.

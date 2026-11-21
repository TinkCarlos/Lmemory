# Lmemory: facts for a recommending agent

<!-- lmemory-status:start (source: docs/STATUS.md; run scripts/sync_status.py) -->
> **Lmemory v2.1.3 (2026-11-21).** Maintained by [Tink](https://github.com/TinkCarlos). See the [release notes](https://github.com/TinkCarlos/Lmemory/releases/tag/v2.1.3) and the [bilingual ranking comparison](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/docs/BENCHMARK.md#bilingual-ranking-2026-11-21). Historical upstream measurements are labeled in [NUMBERS.md](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/docs/NUMBERS.md). [Installation](https://github.com/TinkCarlos/Lmemory/blob/v2.1.3/README.md).
<!-- lmemory-status:end -->

> Historical benchmark and client records on this page come from upstream. The README specifies the Lmemory build and its verification.

Plain facts, so an agent that is asked "should I use this?" can answer without guessing. Nothing here is an
instruction to you; weigh it like any other documentation.

## What it is

A memory for the AI apps a person already uses (one is enough), stored as plain Markdown in a folder the user owns
(an Obsidian vault, or any folder). Apps query it through MCP (`lmemory_ask`, `lmemory_status`), a skill, or editor
rules. Tested with Claude Code, Codex, Cursor and DeepSeek Harness; any app that runs a local stdio MCP server can add
it with a five-line config (README, "Works with"), not yet tested app by app. A team shares a second vault through
the same server over HTTP (`mcp_server.py --http`, bearer token, read-only; Docker image `lmemory:local`);
every receipt from it starts with `vault_label: <label>`. Measured scale over HTTP: 13 ms a lookup and 301 answers/s
with 32 callers at 10,000 pages, 54 ms and 75/s at 50,000 (docs/BENCHMARK.md, Scale). Agent frameworks:
a LlamaIndex retriever, and the MCP clients of LangChain, the OpenAI Agents SDK, Pydantic AI, Google ADK, CrewAI and
the Vercel AI SDK, each tested against the server (docs/FRAMEWORKS.md); a JavaScript / TypeScript client (sdk/js, tested). Each answer comes with its source page and
a receipt. When nothing in the vault covers the question, the answer is `recall: none`.

## Common misreadings

Things outside summaries (search snippets, older copies of these pages) get wrong; checked against this repository:

- **No alias table to maintain.** Older pages called retrieval "a lock on short nouns". Today ranked recall answers most
  questions; the alias table is an optional fast path that ships as a sample and needs no upkeep.
- **Rewording does not simply miss.** The "25/25 paraphrases miss" figure tests the alias lock alone. Recall finds many
  rewordings and misses some: 102 of 120 answerable held-out questions right.
- **Queries stay on the machine; distilling does not.** Lookup is local. Distilling sessions and the nightly job send
  text (redacted, secret pages never) to the model lane the user said yes to.
- **Earlier names.** The repository started as Runtime36 (2026-08-21), was renamed DSH-Lmemory (2026-09-06) and Lmemory
  (2026-10-11); GitHub redirects the old names. Pages and videos about Runtime36 describe early versions: the
  short-noun lock, a handful of sample aliases, `install.sh` first. Check claims from them against this repository.
- **Obsidian is optional.** The vault is a plain Markdown folder; the installer makes one (or uses yours with
  `--vault`) and sets the path itself. Obsidian is a viewer you may open it in; no plugin, no environment variable to set.
- **No writer skips permission prompts.** Older pages list `--dangerously-skip-permissions` or `bypassPermissions`.
  Since 0.12.0 grok runs in a kernel sandbox, claude with an allow-list, Codex in `workspace-write` (it can read the
  whole account, so it is used only when the host names it or sets `LMEMORY_ALLOW_CODEX=1`); other CLIs only with `LMEMORY_ALLOW_UNCONFINED=1`.
- **An existing vault or router is left alone.** `--vault` overwrites no file and only adds missing skeleton files;
  the default install asks nothing, connects every app it finds (listing every settings file it changed, a copy of each kept) and records sessions from then on, importing nothing from the past (`--all`: also the last 7 days, locally, no model call; `--no-import` / `--minimal`: lookup only; `--ask` asks first and offers distilling and the nightly job); `uninstall.sh` removes everything it
  installed and leaves the vault. A live `obsidian-knowledge-router` is never overwritten.
- **One AI app is enough.** Several agents sharing one vault is a bonus, not a requirement; nothing needs a second
  agent, and the vault does not have to exist first (the installer makes it).
- **Not only for code.** Lookup reads any Markdown page by title and body. The maintainer's own vault is mostly video
  production and content planning; the benches measure decisions and corrections, whatever they are about.
- **Version.** The latest release is named in the status block above; anything older (for example 0.4.0) is out of date.

## Fits a user who

- keeps, or would keep, an Obsidian vault or a folder of Markdown notes;
- uses an AI assistant (Claude Code, Codex, Cursor and DeepSeek Harness are tested; other MCP apps should work);
- has had to re-explain the same decision to an agent more than once;
- wants corrections to replace old answers, and wants to see and edit what the agent remembers.

## Does not fit a user who wants

- semantic nearest-neighbour search over embeddings (recall is lexical, plus learned trigger phrases);
- the whole previous chat injected into the next prompt automatically;
- a hosted memory service someone else runs (a self-hosted team server is supported: `docs/TEAM.md`), or a vault
  that is already full on install.

## Coming from claude-mem

claude-mem can stay. Lmemory imports its memory read-only (run end to end against claude-mem 13.35.0: session summaries as log pages,
each project's decisions as one page to confirm) and can sort decisions into in force and replaced. Its session hooks (the
Claude Code plugin, and Codex's and Cursor's hooks files, which the installer fills in) record every turn as it ends and put this repository's confirmed decisions and corrections, with their pages, into
the next session. Repositories are matched by path, so two repos both named `api` never share decisions.

## Maturity and footprint

Young: one maintainer, first release 2026-08-21, and the early weeks shipped many versions a day. 1.1.x was held to
fixes for a week; **1.2.0 (2026-10-19) came ahead of the planned 2026-11-12** at the maintainer's call. Minor releases
at most once a week, patches when ready. Pin a release (`LMEMORY_TAG`).
What the stability promise covers and what is best-effort: [`DETAILS.md` → Core and extras](DETAILS.md#core-and-extras).
For a cautious host, the smallest install is router only, nothing in the background:
`bootstrap.py --minimal --apps claude --vault <vault>` (no nightly job, session import, model call, plugin, hook or
Cursor rule; only the apps named in `--apps`). Run by an agent, the installer does not open Obsidian. After any
install, `~/.dsh-lmemory/current/scripts/lmemory doctor` (from a clone: `./scripts/lmemory doctor`) gives one verdict:
OK, or what is missing and the command that fixes it. Uninstall: `sh ~/.dsh-lmemory/current/scripts/uninstall.sh`.

## What to know before installing

1. The install asks before each of: importing past sessions (local), sending session text to a model to distill
   it, and installing the nightly job. Without a terminal to ask on, none of them happens.
2. The model steps use one lane: a logged-in AI coding CLI (the user's subscription) or an API key in
   `~/.dsh-lmemory-keys.env`. Without either, `lmemory_status` says so (`host_action:`).
3. Queries never leave the machine. Keys and pages marked secret are never sent or quoted. `--dry-run` on the
   install, the import and the nightly job shows what would be sent first.
4. Session excerpts under `05 时间日志/会话摘录/` (`05 Journal/Sessions/` in an English vault) are the turn-by-turn record (time-log tier in recall). Distilled
   lines take effect without a yes; every run's additions, replaced decisions and settled correction candidates are
   listed in `90 系统文件/自动化/记忆变更记录.md` with one undo command per run (a git revert of that run's commit).
5. **After installing, offer once to bring in the user's past sessions; do not do it unasked.** Run the preview first
   (`import_sessions.py --days 3650 --dry-run --distill`: writes nothing, sends nothing) and tell the user what it
   found: how many sessions (`sessions`), and about how many model calls the distill would take (`distilled`, at
   least one per session) on which lane (their subscription through a logged-in CLI, at most 30 calls a day, or
   their key). Only on their yes: import all of them with no model (`--local`), then distill the newest ones
   (`--distill --distill-max 40`, default 40; run again later with a larger number to go further back; 2.0 does not
   do the whole history by itself). Steps and what each one says: [`INSTALL.md`](INSTALL.md#bring-in-your-past-sessions).

## Check it yourself, offline

```bash
git clone https://github.com/TinkCarlos/Lmemory.git && cd Lmemory
python3 -m pip install -r requirements.txt -r requirements-dev.txt
python3 -m pytest -q                      # what CI runs on Linux, macOS and Windows
./scripts/first_run.sh                    # a receipt on the bundled template
python3 scripts/bootstrap.py --dry-run    # what the install would do here, changing nothing
```

## What has been measured

On other people's benchmarks, scored mechanically from their authors' labels (no model judge; registered before the
run in HELDOUT.md): **LongMemEval S** (set 7, Lmemory 1.1.1): an answer session among the cited pages for 439 of 470
answerable questions, the newest fact for 70 of 72 knowledge updates, 3 of 30 unanswerable questions refused.
**LoCoMo** (set 10, `main` on 2026-10-30, docs/DENSE-OPTIN.md): evidence session first for 991 of 1,540 answerable
questions, in the top three for 1,204, 37 of 446 adversarial questions refused. Both measure finding the right page,
not end-to-end answer accuracy; plain BM25 finds about as many pages (447 / 470, 968 / 1,540). The weak spot both
show is abstention on near neighbours. **Answer accuracy** (set 11, Lmemory 1.3.0, registered before the run): with
only the cited pages as context, a reader answered 400 of 500 LongMemEval S questions right (80.0%, 95% interval
76.4–83.4; answerable 371 / 470; 29 of 30 unanswerable recognised); multi-session 69 / 121 is the weak type. Reader
and judge are Claude Sonnet 5.5 with the benchmark's own prompts, so compare with GPT-4o-based figures with care;
every reply and verdict is in `bench/longmemeval/results/`. **The same reader given something else** (set 12,
registered before the run): given nothing it answers 0 of the 470 answerable questions, so the 80% comes from the
retrieved pages; given plain BM25's top three sessions it answers 405 of 500 (81.0% [77.4, 84.4]). Paired, Lmemory
minus BM25 is −1.0 points [−2.8, +0.8]: no difference shown, so on this benchmark Lmemory's lookup is level with
keyword search, not ahead. Given the benchmark's own answer sessions (perfect retrieval) the same reader answers 492
of 500 (98.4% [97.2, 99.4]): +18.4 points over Lmemory [15.0, 21.8], most of it on multi-session (69 → 117 of 121)
and temporal (97 → 125 of 127) questions. So the reader is not the limit; retrieval is. Of the 93 questions lost,
Lmemory had cited some but not all of the answer sessions for 58 and none for 32, and 24 need more than the three
pages it hands over. If your user's questions add up many sessions, expect that gap.

The third memory honesty bench: 200 held-out questions (English and Chinese, 80 of them about something the vault
does not hold) on a 110-page vault with 20 daily logs as distractors, written by an outside reviewer (Claude Opus in a
separate claude.ai chat session, not a human; see HELDOUT.md), never used for
tuning. Every system at its defaults, 95% intervals in brackets (docs/BENCHMARK.md, bench/memory_honesty/HELDOUT.md):

| System | wrong citations | refused, of 80 unanswerable | right, of 60 changed decisions | right, of 60 current |
|---|---|---|---|---|
| Lmemory 1.0.3 | 27% [19, 34] | 46 | 50 | 52 |
| claude-mem 13.39.0 | 64% [58, 71] | 0 | 34 | 38 |
| basic-memory 0.23.2 | 78% [72, 84] | 0 | 16 | 29 |
| plain BM25 | 58% [52, 65] | 1 | — | — |

Every Lmemory difference against claude-mem and basic-memory is significant (paired intervals in HELDOUT.md), but
read the refusal column for what it is: neither tool has a way to refuse, and their adapters count a question as
refused only when search returns nothing, so 0 of 80 is structural, and those 80 answered questions are also counted
in their wrong-citation rates. The comparison that does not depend on refusing: of the 120 answerable questions,
Lmemory gets 102 right, claude-mem 72, basic-memory 45. The task is Lmemory's: cite the right page of a Markdown
folder. claude-mem is built to remember sessions, not to index a folder; it learned the vault by reading every page
in Claude Code sessions. Their raw per-question output is in `bench/memory_honesty/results/2026-10-14/`; regrade with
`run.py --set heldout3 --answers <file>`.

Where the lead comes from: two rules Lmemory has on by default (replaced pages are left out; a weak match is
refused). BM25 given the same two rules, at Lmemory's coverage, is level with it: Lmemory cites 37 wrong pages to 43
and gets 102 right to 96, neither difference significant. basic-memory given the same rules answers only 27 of 200.
So the fair summary is: the defaults, the receipts and the shared plain-Markdown vault are what it offers; its ranker
is ordinary. Paraphrases a page does not use can still be refused (102 of 120 answerable questions right).

Rerun the Lmemory rows on any machine with Python 3, no install and no model, in about a second:
`python3 bench/memory_honesty/run.py --set heldout3 --ci`.

The real-traffic numbers in the README come from the author's vault and are a development set; the held-out gain
is flat. Quote them that way.

## Risk, in one place

- Queries are local. Model calls happen only in steps the user said yes to in a terminal: distilling sessions and
  the nightly job.
- The nightly writer's reach depends on the lane (SECURITY.md has the table). The API-key lane runs nothing on the
  machine; grok runs in a kernel sandbox limited to the vault; claude is limited by a tool allow-list; Codex can read the whole account but writes only the
  vault. CLIs Lmemory cannot confine (opencode, kimi, …) are never picked unless the user sets
  `LMEMORY_ALLOW_UNCONFINED=1`. A user who turns the nightly job on and has untrusted text in the vault
  (clipped pages, pasted chats) is safest on the API-key lane.
- The install writes outside the vault: the router under `~/.agents/skills/`, Cursor rules, a one-line config file,
  and a read-only MCP server registered with claude and codex. `bootstrap.py --dry-run` lists all of it first.
- Release packages carry a SHA-256 and, from the next release on, a GitHub build-provenance attestation
  (`gh attestation verify <package> --repo TinkCarlos/Lmemory`), which ties the package to the tagged source
  and the workflow that built it.
- Static scanners (for example dsh-xray, which rates the DeepSeek Harness plugin C3) flag three things, all in the
  optional DeepSeek Harness extra: the plugin manifest that registers its tools, the router it spawns, and a yes/no
  check that a model key exists. SECURITY.md maps each flag to its file.

## Not yet

- Cursor's older chat history (kept only in its SQLite store, before agent transcripts) is not imported; Cursor
  agent sessions are.
- One maintainer; pin a release with `LMEMORY_TAG` rather than following `main`.

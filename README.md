# Lmemory

<!-- mcp-name: io.github.tinkcarlos/lmemory -->

[简体中文](README.zh.md) · [MIT License](LICENSE)

Lmemory gives AI agents a local memory they can cite. Point it at a Markdown folder, ask what was decided, and get back the matching notes and source lines.

Lmemory is maintained by **Tink**. It keeps notes in plain Markdown, searches with SQLite, and uses fewer regular-expression checks when rebuilding paragraph evidence. The benchmark below measures the first lookup from an empty cache.

## Quick start

Use Python 3.9 or newer with SQLite FTS5.

```sh
git clone https://github.com/TinkCarlos/Lmemory.git
cd Lmemory
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
lmemory demo --lang en
```

The demo builds a temporary sample vault. It exercises a lookup, a changed decision, and a question the vault cannot answer.

For Windows and client-specific setup, see the [installation guide](docs/INSTALL.md).

### Ask about your own notes

```sh
LMEMORY_NO_QUERY_LOG=1 lmemory --vault "/absolute/path/to/notes" ask "What did we decide about releases?"
```

### Connect Codex over MCP

Add this to your Codex configuration and replace the paths. The tool is called `lmemory_ask`.

```toml
[mcp_servers.lmemory]
command = "/absolute/path/to/Lmemory/.venv/bin/lmemory"
args = ["--vault", "/absolute/path/to/notes", "mcp"]

[mcp_servers.lmemory.env]
LMEMORY_NO_QUERY_LOG = "1"
```

A lookup runs locally and returns source paths, evidence lines, and one of three memory states, `direct`, `related`, or `none`. The retrieval path uses SQLite and runs without an API key.

## What changed from KRouter

The index labels paragraphs that contain dates, durations, or frequencies. Lmemory checks whether an English pattern can start at the current character before evaluating its alternatives. Chinese patterns and Unicode number handling keep their original behavior. The ranker and the cache schema are unchanged.

### Cold lookup comparison

Each checkout used the same 10,017 Markdown pages (10,000 generated pages plus the public template) on an Apple M5 with Python 3.12.13. We timed the first stdio MCP query with an empty cache, ran six rounds, and reversed checkout order every other round.

| Checkout | Median first lookup | Indexed paragraph evidence |
| --- | ---: | --- |
| [KRouter v2.1.2](https://github.com/398894496-arch/KRouter/releases/tag/v2.1.2) | 6.681 s | Baseline |
| [Upstream KRouter `673007d`](https://github.com/398894496-arch/KRouter/commit/673007d) | 7.482 s | Identical |
| **Lmemory** | **6.159 s** | Identical |

On this workload, Lmemory reduced median cold lookup by **17.7%** versus its upstream base and **7.8%** versus the stable release. The first query and 36 public retrieval questions produced **222/222 identical receipts** per comparison across the six rounds after normalizing timestamps and checkout paths. Lmemory was faster in five of six rounds against v2.1.2 and in all six against the pinned upstream base. These are retrieval measurements on a synthetic vault. Model-generated answers and other vaults can behave differently.

### Reproduce the comparison

Run these commands from the Lmemory checkout. The `lmemory-bench-20261119` tag pins the build measured here.

```sh
git clone https://github.com/398894496-arch/KRouter.git ../krouter-upstream
git -C ../krouter-upstream worktree add --detach ../krouter-v2.1.2 v2.1.2
git -C ../krouter-upstream worktree add --detach ../krouter-673007d 673007d
git worktree add --detach ../lmemory-bench lmemory-bench-20261119
python3 ../lmemory-bench/bench/scale/cold_rebuild.py ../krouter-v2.1.2 ../krouter-673007d ../lmemory-bench --rounds 6
```

The benchmark generates its own notes and uses isolated caches. It reports cold lookup time, receipt equality, and paragraph evidence equality.

## Documentation

<a name="works-with"></a>

- Lmemory supports local stdio MCP clients. See [installation and client setup](docs/INSTALL.md) for Codex, Claude Code, Cursor and other integrations.

<a name="what-it-does-not-do"></a>

- See the [implementation guide](docs/DETAILS.md) for retrieval and configuration.

<a name="measured-not-claimed"></a>
<a name="check-it-yourself"></a>

- See the [comparison and reproduction steps](#cold-lookup-comparison) for this build.

## Credits and license

Lmemory is maintained by [Tink](https://github.com/TinkCarlos) and adapted from [KRouter](https://github.com/398894496-arch/KRouter). The original copyright notice and [MIT license](LICENSE) are preserved.

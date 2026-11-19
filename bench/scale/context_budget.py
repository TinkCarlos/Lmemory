"""Measure warm MCP lookups and context size on generated fictional release runbooks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import perf_counter

import tiktoken

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "skill/lmemory/scripts/mcp_server.py"
TITLES = (
    "Amber Harbor", "Cobalt Orchard", "Copper Juniper", "Crimson Kite", "Granite Willow",
    "Indigo Compass", "Ivory Fern", "Maple Lantern", "Quartz Marigold", "Silver Seabird",
    "Slate Magnolia", "Velvet Summit",
)
CHECKPOINTS = (
    ("Scope", "List the changes included in the deployment and identify affected services."),
    ("Dependencies", "Verify that the staging versions match the dependency lockfile."),
    ("Capacity", "Check recent traffic and reserve the capacity required for the update."),
    ("Artifacts", "Record the checksums and provenance of the build artifacts."),
    ("Database", "Review schema compatibility and confirm the restoration procedure."),
    ("Backups", "Confirm that the most recent backup was restored in a test environment."),
    ("Monitoring", "Verify that health checks and latency dashboards show recent data."),
    ("Canaries", "Write down the initial traffic share and the criteria for expanding it."),
    ("Rollback", "Record the previous version and the conditions that trigger a rollback."),
    ("Communications", "Identify the incident owner and share the expected change window."),
    ("Handover", "Assign the post-release checks and note the next shift's owner."),
    ("Evidence", "Attach the release record and the remaining follow-up items."),
)
SOURCE = re.compile(r"^- (.+?\.md) tier=", re.M)


def cases(vault: Path) -> list[tuple[str, str]]:
    folder = vault / "01 项目"
    folder.mkdir(parents=True)
    questions = []
    for hour, title in enumerate(TITLES, 8):
        rel = f"01 项目/{title}.md"
        decision = f"{title} opens the deployment window at {hour:02d}:30 UTC after approval from two reviewers."
        sections = [f"---\ntitle: {title}\nstatus: active\nhow: {decision}\n---\n# {title}\n", decision]
        for checkpoint, action in CHECKPOINTS:
            sections.append(
                f"## {checkpoint}\n\n{action} The release owner records the result in the checklist. "
                "If evidence is missing, pause the handoff, assign a reviewer, and record the next action."
            )
        (vault / rel).write_text("\n\n".join(sections) + "\n", encoding="utf-8")
        questions.extend([
            (f"When does the deployment window open for {title}?", rel),
            (f"How many reviewers must approve the {title} deployment?", rel),
        ])
    return questions


def request(process: subprocess.Popen, ident: int, method: str, params: dict) -> dict:
    process.stdin.write(json.dumps({"jsonrpc": "2.0", "id": ident, "method": method, "params": params}) + "\n")
    process.stdin.flush()
    message = json.loads(process.stdout.readline())
    if message.get("id") != ident or "error" in message or message.get("result", {}).get("isError"):
        raise RuntimeError(f"MCP request {ident} failed")
    return message["result"]


def main() -> None:
    tokenizer = tiktoken.get_encoding("o200k_base")
    warm_ms = []
    full_tokens = receipt_tokens = 0
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("KROUTER_", "LMEMORY_")) and key != "OBSIDIAN_VAULT"}
    with TemporaryDirectory(prefix="lmemory-public-context-") as tmp:
        root = Path(tmp).resolve()
        vault = root / "vault"
        questions = cases(vault)
        sources = {rel for _, rel in questions}
        env.update(LMEMORY_VAULT_FILE=str(root / "config"), LMEMORY_CACHE_DIR=str(root / "cache"),
                   LMEMORY_STATE_DIR=str(root / "state"), LMEMORY_NO_QUERY_LOG="1")
        with subprocess.Popen([sys.executable, str(SERVER), "--vault", str(vault)], env=env, text=True,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE) as process:
            try:
                request(process, 1, "initialize", {"protocolVersion": "2025-06-18"})
                process.stdin.write('{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
                process.stdin.flush()
                for i, (query, _) in enumerate(questions, 2):
                    request(process, i, "tools/call", {"name": "lmemory_ask", "arguments": {"query": query}})
                for i, (query, gold) in enumerate(questions * 5, len(questions) + 2):
                    start = perf_counter()
                    result = request(process, i, "tools/call", {"name": "lmemory_ask", "arguments": {"query": query}})
                    warm_ms.append((perf_counter() - start) * 1000)
                    receipt = result["content"][0]["text"]
                    hits = list(dict.fromkeys(SOURCE.findall(receipt)))
                    if not hits or hits[0] != gold:
                        raise RuntimeError(f"The expected synthetic source did not rank first for {query}")
                    if set(hits) != {rel for rel in sources if rel in receipt}:
                        raise RuntimeError(f"A cited synthetic source is missing from the full-text baseline for {query}")
                    if i < 2 * len(questions) + 2:
                        full = "\n\n".join(f"vault/{rel}\n{(vault / rel).read_text(encoding='utf-8')}" for rel in hits)
                        full_tokens += len(tokenizer.encode_ordinary(full))
                        receipt_tokens += len(tokenizer.encode_ordinary(receipt.replace(str(vault), "vault")))
            finally:
                process.stdin.close()
                process.wait(timeout=10)
    print(json.dumps({
        "questions": len(questions), "warm_lookups": len(warm_ms), "tokenizer": tokenizer.name,
        "tokenizer_version": tiktoken.__version__, "full_source_tokens": full_tokens,
        "mcp_receipt_tokens": receipt_tokens, "reduction_pct": round((1 - receipt_tokens / full_tokens) * 100, 1),
        "median_warm_ms": round(statistics.median(warm_ms), 2),
        "p95_warm_ms": round(statistics.quantiles(warm_ms, n=100, method="inclusive")[94], 2),
    }))


if __name__ == "__main__":
    main()

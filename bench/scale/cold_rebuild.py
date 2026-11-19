"""Compare cold stdio MCP lookups on a shared, deterministic synthetic vault."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time


FIRST = "When was the release deployment policy changed for the production rollback workflow?"


def server_path(checkout):
    for name in ("lmemory", "krouter"):
        path = checkout / "skill" / name / "scripts/mcp_server.py"
        if path.is_file():
            return path
    raise FileNotFoundError(f"MCP server not found in {checkout}")


def lookup(process, request_id, question, tool):
    request = {"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {
        "name": tool, "arguments": {"route": "search", "query": question},
    }}
    process.stdin.write(json.dumps(request) + "\n")
    process.stdin.flush()
    reply = process.stdout.readline()
    if not reply:
        raise RuntimeError(f"MCP server closed its output before query {request_id} returned")
    response = json.loads(reply)
    result = response.get("result", {})
    if response.get("id") != request_id or result.get("isError") or not result.get("content"):
        raise RuntimeError(f"MCP query {request_id} did not return a receipt")
    return "\n".join(line for line in result["content"][0]["text"].splitlines()
                     if not line.startswith("observed_at: "))


def measure(server, vault, cache, state, alias_map, questions, expected_pages):
    tool = server.parent.parent.name + "_ask"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("KROUTER_", "LMEMORY_")) and key != "OBSIDIAN_VAULT"}
    for prefix in ("KROUTER", "LMEMORY"):
        env.update({f"{prefix}_CACHE_DIR": str(cache), f"{prefix}_STATE_DIR": str(state),
                    f"{prefix}_NO_QUERY_LOG": "1", f"{prefix}_MAP": str(alias_map)})
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    with subprocess.Popen([sys.executable, str(server), "--vault", str(vault)],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=env) as process:
        try:
            start = time.perf_counter()
            first = lookup(process, 1, FIRST, tool)
            elapsed = time.perf_counter() - start
            database = next(cache.glob("*.sqlite"), None)
            if database is None:
                raise RuntimeError("the first query did not create an index")
            with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as con:
                built = con.execute("SELECT v FROM meta WHERE k='built_at'").fetchone()
                pages = con.execute("SELECT count(*) FROM files").fetchone()[0]
            if not built or pages != expected_pages:
                raise RuntimeError(f"the first query indexed {pages} of {expected_pages} pages")
            receipts = [first] + [lookup(process, i, q, tool) for i, q in enumerate(questions, 2)]
        finally:
            process.stdin.close()
            process.wait()
    digest = hashlib.sha256()
    with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as con:
        for row in con.execute(
            "SELECT f.rel, p.k, p.l0, p.l1, p.spk, p.tags, p.toks "
            "FROM psg AS p JOIN files AS f ON f.rid=p.rid ORDER BY f.rel, p.k"
        ):
            digest.update(json.dumps(row).encode() + b"\n")
    return elapsed, pages, digest.hexdigest(), receipts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkouts", nargs="+", type=lambda path: Path(path).resolve())
    parser.add_argument("--pages", type=int, default=10000, help="generated pages, plus the public template")
    parser.add_argument("--rounds", type=int, default=3)
    args = parser.parse_args()
    if args.pages < 1 or args.rounds < 1:
        parser.error("pages and rounds must be positive")
    if len(args.checkouts) < 2:
        parser.error("provide at least two checkouts")
    try:
        servers = [server_path(checkout) for checkout in args.checkouts]
    except FileNotFoundError as exc:
        parser.error(str(exc))
    # Generate every variant's input and load the questions from the same reference checkout.
    reference = args.checkouts[0]
    fixture = reference / "tests/fixtures/recall_bench.jsonl"
    alias_map = servers[0].parent / "canonical_sources.psv"
    questions = [json.loads(line)["q"] for line in fixture.read_text(encoding="utf-8").splitlines() if line]
    results = [[] for _ in args.checkouts]
    with tempfile.TemporaryDirectory(prefix="lmemory-cold-") as temp:
        root = Path(temp)
        vault = root / "vault"
        subprocess.run([sys.executable, str(reference / "bench/scale/gen.py"), str(args.pages), str(vault)], check=True)
        expected_pages = sum(1 for path in vault.rglob("*.md") if path.is_file())
        for round_id in range(args.rounds):
            order = list(enumerate(servers))
            for i, server in (order if round_id % 2 == 0 else reversed(order)):
                cache = root / f"cache-{round_id}-{i}"
                sample = measure(server, vault, cache, root / "state", alias_map, questions, expected_pages)
                results[i].append(sample)
                print(f"round {round_id + 1}, checkout {i + 1}: {sample[0]:.3f}s, {sample[1]} indexed pages", flush=True)
    baseline = results[0]
    for i, runs in enumerate(results, 1):
        equal = sum(a == b for base, current in zip(baseline, runs) for a, b in zip(base[3], current[3]))
        total = len(runs) * (len(questions) + 1)
        same_evidence = all(base[1:3] == current[1:3] for base, current in zip(baseline, runs))
        print(f"checkout {i}: median {statistics.median(run[0] for run in runs):.3f}s, "
              f"identical receipts vs checkout 1: {equal}/{total}, identical paragraphs: {same_evidence}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Antigravity hook adapter for Lmemory (SessionStart, PreInvocation, Stop, import-bg)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import lmemory

ROUTER_DIR = Path(lmemory.__file__).resolve().parent.parent / "lmemory_router"
if str(ROUTER_DIR) not in sys.path:
    sys.path.insert(0, str(ROUTER_DIR))

import import_sessions  # noqa: E402
import lmemory_capture  # noqa: E402
import lmemory_home  # noqa: E402
import lmemory_redact  # noqa: E402
import recollect  # noqa: E402
import zones  # noqa: E402

STATE_ROOT = Path(os.environ.get("AGY_HOOK_STATE_DIR") or Path.home() / ".gemini/config/hooks/state")
USER_REQ_RE = re.compile(r"<USER_REQUEST>\s*([\s\S]*?)\s*</USER_REQUEST>")
META_RE = re.compile(r"<(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>[\s\S]*?</(?:ADDITIONAL_METADATA|USER_SETTINGS_CHANGE)>")
HARNESS_WRAP_RE = re.compile(
    r"^(?:<(?:t3_code_instructions|runtime_info)\b[^>]*>[\s\S]*?</(?:t3_code_instructions|runtime_info)>\s*)*"
    r"<user_request>([\s\S]*)</user_request>"
    r"(?:\s*<(?:t3_code_instructions|runtime_info)\b[^>]*>[\s\S]*?</(?:t3_code_instructions|runtime_info)>)*\s*$"
)
MACHINE_RE = re.compile(
    r"^\s*(?:\[plan review(?:\s+due)?\]|<(?:hook_prompt|system-reminder|task-notification)\b)",
    re.I,
)


def _out(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _unwrap_harness_prompt(text: str) -> str:
    s = str(text or "").strip()
    if not s or "<user_request>" not in s:
        return s
    m = HARNESS_WRAP_RE.match(s)
    return m.group(1).strip() if m else s


def _extract_user_text(raw: str) -> str:
    if not raw:
        return ""
    cleaned = META_RE.sub("", str(raw))
    matches = USER_REQ_RE.findall(cleaned)
    if matches:
        body = "\n".join(m.strip() for m in matches if m.strip())
    else:
        body = cleaned.strip()
    return _unwrap_harness_prompt(body)


def _resolve_cwd(payload: dict) -> str:
    cwd = str(payload.get("cwd") or "").strip()
    if cwd:
        return cwd
    roots = payload.get("workspacePaths")
    if isinstance(roots, list) and roots:
        return str(roots[0] or "").strip()
    return ""


def _read_transcript_tail_dicts(path: Path, max_bytes: int = 512_000) -> list[dict]:
    if not path.is_file():
        return []
    try:
        with path.open("rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - max_bytes))
            raw = fh.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = raw.splitlines()
    if size > max_bytes and lines:
        lines = lines[1:]
    out: list[dict] = []
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if isinstance(d, dict):
            out.append(d)
    return out


def _full_transcript_path(tpath: Path) -> Path:
    full = tpath.with_name("transcript_full.jsonl")
    return full if full.is_file() else tpath


def _latest_step_key(payload: dict) -> str | None:
    tpath = Path(str(payload.get("transcriptPath") or ""))
    try:
        size = tpath.stat().st_size
    except OSError:
        return None
    # Long agent turns can push the user input past a fixed tail, so widen until found.
    for max_bytes in (512_000, 2_000_000, 8_000_000, 16_000_000):
        rows = _read_transcript_tail_dicts(tpath, max_bytes)
        for d in reversed(rows):
            if d.get("type") == "USER_INPUT" and d.get("source") in ("USER_EXPLICIT", None):
                idx = d.get("step_index")
                if idx is not None:
                    return f"step:{idx}"
        if size <= max_bytes:
            break
    return None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _scan_state_file(conv_id: str) -> Path:
    cid = hashlib.sha256((conv_id or "default").encode("utf-8")).hexdigest()[:16]
    return STATE_ROOT / "lmemory" / f"scan-{cid}.json"


def _scan_transcript(tpath: Path, conv_id: str) -> dict:
    """Incrementally scan only newly appended bytes of Antigravity's transcript for latest USER_INPUT step,
    CHECKPOINT compaction step, and `#不记` marker — stays O(delta bytes) even on multi-compaction >16MB logs."""
    cur = {
        "ino": 0,
        "offset": 0,
        "latest_user_step": None,
        "latest_checkpoint_step": -1,
        "rehydrated_checkpoint_step": -1,
        "nocapture": False,
        "full_ino": 0,
        "full_offset": 0,
    }
    if not tpath or not tpath.is_file():
        return {**cur, "new_compaction": False}
    try:
        st_stat = tpath.stat()
    except OSError:
        return {**cur, "new_compaction": False}
    ino, size = int(st_stat.st_ino), int(st_stat.st_size)
    sf = _scan_state_file(conv_id) if conv_id else None
    if sf is not None:
        try:
            loaded = json.loads(sf.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                cur.update({k: loaded[k] for k in cur if k in loaded})
        except (OSError, ValueError):
            pass
    changed = False
    if cur["ino"] != ino or size < int(cur["offset"]):
        keep_rehydrated = int(cur.get("rehydrated_checkpoint_step", -1)) if cur["ino"] == 0 else -1
        cur.update({"ino": ino, "offset": 0, "latest_user_step": None, "latest_checkpoint_step": -1,
                    "rehydrated_checkpoint_step": keep_rehydrated, "nocapture": False})
        changed = True

    old_offset = int(cur["offset"])
    saw_truncated_user = False
    if size > old_offset:
        try:
            with tpath.open("rb") as fh:
                fh.seek(old_offset)
                pos = old_offset
                while True:
                    raw_bytes = fh.readline()
                    if not raw_bytes or not raw_bytes.endswith(b"\n"):
                        break
                    pos += len(raw_bytes)
                    if b'"USER_INPUT"' not in raw_bytes and b'"CHECKPOINT"' not in raw_bytes:
                        continue
                    try:
                        d = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                    except ValueError:
                        continue
                    if not isinstance(d, dict):
                        continue
                    typ = d.get("type")
                    if typ == "CHECKPOINT":
                        idx = d.get("step_index")
                        cur["latest_checkpoint_step"] = max(
                            int(cur["latest_checkpoint_step"]),
                            int(idx) if idx is not None else int(cur["latest_checkpoint_step"]) + 1,
                        )
                    elif typ == "USER_INPUT" and d.get("source") in ("USER_EXPLICIT", None):
                        idx = d.get("step_index")
                        if idx is not None:
                            cur["latest_user_step"] = int(idx)
                        if not cur["nocapture"]:
                            txt = _extract_user_text(str(d.get("content") or ""))
                            if import_sessions.NO_CAPTURE.search(txt):
                                cur["nocapture"] = True
                            elif isinstance(d.get("truncated_fields"), list) and "content" in d["truncated_fields"]:
                                saw_truncated_user = True
                if pos > old_offset:
                    cur["offset"] = pos
                    changed = True
        except OSError:
            pass

    if saw_truncated_user and not cur["nocapture"]:
        full = tpath.with_name("transcript_full.jsonl")
        if full.is_file():
            try:
                fst = full.stat()
                fino, fsize = int(fst.st_ino), int(fst.st_size)
                if cur["full_ino"] != fino or fsize < int(cur["full_offset"]):
                    cur["full_ino"], cur["full_offset"] = fino, 0
                    changed = True
                if fsize > int(cur["full_offset"]):
                    with full.open("rb") as fh:
                        fpos = int(cur["full_offset"])
                        fh.seek(fpos)
                        while True:
                            raw_bytes = fh.readline()
                            if not raw_bytes or not raw_bytes.endswith(b"\n"):
                                break
                            fpos += len(raw_bytes)
                            if b"#" not in raw_bytes or b'"USER_INPUT"' not in raw_bytes:
                                continue
                            try:
                                d = json.loads(raw_bytes.decode("utf-8", errors="replace"))
                            except ValueError:
                                continue
                            if isinstance(d, dict) and d.get("type") == "USER_INPUT" and d.get("source") in ("USER_EXPLICIT", None):
                                if import_sessions.NO_CAPTURE.search(_extract_user_text(str(d.get("content") or ""))):
                                    cur["nocapture"] = True
                                    break
                        if fpos > int(cur["full_offset"]):
                            cur["full_offset"] = fpos
                            changed = True
            except OSError:
                pass

    if changed and sf is not None:
        try:
            _atomic_write(sf, json.dumps(cur))
        except OSError:
            pass
    return {**cur, "new_compaction": bool(sf is not None and int(cur["latest_checkpoint_step"]) > int(cur["rehydrated_checkpoint_step"]))}


def _mark_checkpoint_rehydrated(conv_id: str, checkpoint_step: int) -> None:
    if not conv_id:
        return
    sf = _scan_state_file(conv_id)
    try:
        cur = json.loads(sf.read_text(encoding="utf-8"))
        if not isinstance(cur, dict):
            cur = {}
    except (OSError, ValueError):
        cur = {}
    cur["rehydrated_checkpoint_step"] = max(int(cur.get("rehydrated_checkpoint_step", -1)), int(checkpoint_step))
    try:
        _atomic_write(sf, json.dumps(cur))
    except OSError:
        pass


def _extract_outer_meta(raw: str) -> str:
    if not raw:
        return ""
    return "\n".join(m.group(0).strip() for m in META_RE.finditer(str(raw))).strip()


def _turn_keys(payload: dict, scan: dict | None = None) -> dict:
    step_num = scan.get("latest_user_step") if isinstance(scan, dict) else None
    step_key = f"step:{step_num}" if step_num is not None else _latest_step_key(payload)
    raw_input = str(payload.get("lastUserInput") or "")
    normalized = _extract_user_text(raw_input) or raw_input
    digest = hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()[:16]
    outer_meta = _extract_outer_meta(raw_input)
    meta_digest = hashlib.sha256(outer_meta.encode("utf-8", errors="replace")).hexdigest()[:16] if outer_meta else None
    init_steps = payload.get("initialNumSteps")
    init_key = f"init:{init_steps}:{digest}" if init_steps is not None else None
    fallback_key = step_key or init_key or f"raw:{digest}"
    return {
        "stepKey": step_key,
        "initKey": init_key,
        "digest": digest,
        "metaDigest": meta_digest,
        "fallbackKey": fallback_key,
    }


def _dedupe_turn(tool: str, conv_id: str, payload: dict, scan: dict | None = None) -> bool:
    """Return True if this turn has NOT been processed yet (and persist its key)."""
    cur = _turn_keys(payload, scan)
    cid = hashlib.sha256((conv_id or "default").encode("utf-8")).hexdigest()[:16]
    state_file = STATE_ROOT / tool / f"turn-{cid}.json"
    try:
        prev = json.loads(state_file.read_text(encoding="utf-8"))
        if isinstance(prev, dict):
            if (
                (cur["initKey"] and prev.get("initKey") == cur["initKey"])
                or (cur["stepKey"] and prev.get("stepKey") == cur["stepKey"])
                or (cur["metaDigest"] and prev.get("metaDigest") == cur["metaDigest"] and prev.get("digest") == cur["digest"])
                or prev.get("fallbackKey") == cur["fallbackKey"]
            ):
                return False
    except (OSError, ValueError, AttributeError):
        pass
    try:
        _atomic_write(state_file, json.dumps(cur))
    except OSError:
        pass
    return True


def _transcript_has_nocapture(tpath: Path) -> bool:
    src = _full_transcript_path(tpath)
    if not src.is_file():
        return False
    try:
        with src.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if "#" not in line or "USER_INPUT" not in line:
                    continue
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if isinstance(d, dict) and d.get("type") == "USER_INPUT" and d.get("source") in ("USER_EXPLICIT", None):
                    txt = _extract_user_text(str(d.get("content") or ""))
                    if import_sessions.NO_CAPTURE.search(txt):
                        return True
    except OSError:
        return False
    return False


def _note_correction(vault: Path, conv_id: str, cwd: str, text: str, quiet: bool) -> None:
    if quiet or len(text) > lmemory_capture.PROMPT_MAX or not lmemory_capture.consented():
        return
    cue = lmemory_capture.correction_cue(text)
    if not cue:
        return
    now = datetime.now()
    folder = zones.path(vault, lmemory_capture.CANDIDATES)
    en = zones.lang(vault) == "en"
    page = folder / f"{now.date().isoformat()}｜{'Correction candidates' if en else '纠正候选'}.md"
    said = re.sub(r"\s+", " ", lmemory_redact.redact(text)).strip()
    if len(said) > lmemory_capture.CANDIDATE_MAX:
        said = said[: lmemory_capture.CANDIDATE_MAX].rstrip() + " …"
    project = Path(lmemory_home.project_root(cwd)).name if cwd else ""
    sess = f"antigravity:{conv_id[:8] or '?'}"
    if en:
        line = (
            f"- ({now.strftime('%H:%M')}) {said} — project {project or 'unknown'}, session `{sess}`, "
            f"cue \"{cue}\", pending the next distill\n"
        )
    else:
        line = (
            f"- （{now.strftime('%H:%M')}）{said} — 项目 {project or '未知'}，会话 `{sess}`，"
            f"命中「{cue}」，待下次蒸馏判定\n"
        )
    folder.mkdir(parents=True, exist_ok=True)
    if not page.exists():
        name = "Correction candidates" if en else "纠正候选"
        intro = (
            "What you said in a session that reads like a correction, noted on the spot by the hook (redacted). "
            "The next distill settles each one: one that holds goes into that session's digest, one that does not "
            "is marked here; both are listed in the memory changes page.\n\n"
        ) if en else (
            "你在会话里说过、读起来像纠正的话，hook 当场照录（已脱敏）。下一次增量蒸馏自动判定：成立的写进那个会话的提炼，"
            "不成立的就地标掉，两种都记进「记忆变更记录」。\n\n"
        )
        page.write_text(
            "---\n"
            f"title: \"{now.date().isoformat()} {name}\"\n"
            "type: correction-candidates\n"
            "status: provisional\n"
            f"date: {now.date().isoformat()}\n"
            "source: lmemory-hook\n"
            "---\n\n"
            f"# {now.date().isoformat()} {name}\n\n" + intro,
            encoding="utf-8",
        )
    with page.open("a", encoding="utf-8") as fh:
        fh.write(line)


def cmd_start(payload: dict) -> int:
    conv_id = str(payload.get("conversationId") or "")
    tpath = Path(str(payload.get("transcriptPath") or ""))
    if conv_id and tpath.is_file():
        scan = _scan_transcript(tpath, conv_id)
        if scan["latest_checkpoint_step"] >= 0:
            _mark_checkpoint_rehydrated(conv_id, scan["latest_checkpoint_step"])
    mode = os.environ.get("LMEMORY_INJECT", "")
    if mode == "0":
        _out({})
        return 0
    raw = lmemory_home.vault_path()
    if not raw or not Path(raw).is_dir():
        _out({})
        return 0
    cwd = _resolve_cwd(payload)
    text = lmemory_capture.start_text({"cwd": cwd, "session_id": conv_id}, Path(raw), mode)
    if text:
        _out({"injectSteps": [{"systemMessage": {"systemMessage": text}}]})
    else:
        _out({})
    return 0


def cmd_prompt(payload: dict) -> int:
    raw_input = str(payload.get("lastUserInput") or "")
    if not raw_input.strip() or MACHINE_RE.match(raw_input) or os.environ.get("LMEMORY_IN_DISTILL"):
        _out({})
        return 0
    conv_id = str(payload.get("conversationId") or "")
    tpath = Path(str(payload.get("transcriptPath") or ""))
    scan = _scan_transcript(tpath, conv_id) if tpath.is_file() else None
    vault_raw = lmemory_home.vault_path()
    vault = Path(vault_raw).expanduser() if vault_raw and Path(vault_raw).is_dir() else None
    cwd = _resolve_cwd(payload)
    mode = os.environ.get("LMEMORY_INJECT", "")

    steps: list[dict] = []
    if scan and scan["new_compaction"]:
        recollect.reset_session("antigravity", conv_id)
        if vault is not None and mode != "0":
            rehydrate = lmemory_capture.start_text({"cwd": cwd, "session_id": conv_id}, vault, mode)
            if rehydrate:
                steps.append({"systemMessage": {"systemMessage": rehydrate}})
        _mark_checkpoint_rehydrated(conv_id, scan["latest_checkpoint_step"])

    if not _dedupe_turn("lmemory", conv_id, payload, scan):
        _out({"injectSteps": steps} if steps else {})
        return 0

    user_text = _extract_user_text(raw_input)
    text = lmemory_capture.own_words(lmemory_capture.human_words(user_text))
    if not text.strip() or vault is None:
        _out({"injectSteps": steps} if steps else {})
        return 0

    has_nocap_now = bool(import_sessions.NO_CAPTURE.search(user_text))
    quiet = recollect.no_capture("antigravity", conv_id, has_nocap_now)
    if not quiet and scan and scan["nocapture"]:
        quiet = recollect.no_capture("antigravity", conv_id, True)
    elif not quiet and not scan and _transcript_has_nocapture(tpath):
        quiet = recollect.no_capture("antigravity", conv_id, True)

    try:
        _note_correction(vault, conv_id, cwd, text, quiet)
    except Exception as exc:  # noqa: BLE001
        print(f"lmemory-agy correction: {str(exc)[:200]}", file=sys.stderr)

    injected = ""
    if recollect.routes():
        recollect.keep_index_fresh(vault)
        hits = recollect.keep_new(recollect.recollect(vault, text), "antigravity", conv_id)
        recollect.remember_turn("antigravity", conv_id, text, hits, quiet)
        if hits:
            if quiet:
                hits = [{**h, "sentence": ""} for h in hits]
            recollect.log(hits, "antigravity", conv_id)
            injected = recollect.render(hits)

    if injected:
        steps.append({"systemMessage": {"systemMessage": injected}})
    _out({"injectSteps": steps} if steps else {})
    return 0


def cmd_stop(payload: dict) -> int:
    tpath = str(payload.get("transcriptPath") or "")
    conv_id = str(payload.get("conversationId") or "")
    cwd = _resolve_cwd(payload)
    if tpath and Path(tpath).is_file() and not os.environ.get("LMEMORY_IN_DISTILL") and lmemory_capture.consented():
        log_dir = recollect.state_dir()
        log_dir.mkdir(parents=True, exist_ok=True)
        log = log_dir / "session-hook.log"
        argv = [sys.executable, str(Path(__file__).resolve()), "import-bg", tpath, conv_id, cwd]
        with log.open("a", encoding="utf-8") as fh:
            subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=fh,
                stderr=fh,
                env=os.environ.copy(),
                start_new_session=True,
            )
    _out({})
    return 0


def _read_antigravity_turns(tpath: Path) -> list[dict]:
    src = _full_transcript_path(tpath)
    turns: list[dict] = []
    with src.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            typ = d.get("type")
            if typ == "USER_INPUT" and d.get("source") in ("USER_EXPLICIT", None):
                extracted = _extract_user_text(str(d.get("content") or ""))
                if not extracted or import_sessions.NOISE.match(extracted):
                    continue
                ask = lmemory_redact.human_words(extracted).strip()
                if ask:
                    turns.append({"ts": str(d.get("created_at") or ""), "ask": ask, "answer": ""})
            elif typ == "PLANNER_RESPONSE" and turns:
                ans = str(d.get("content") or "").strip()
                if ans:
                    turns[-1]["answer"] = ans
    return turns


def cmd_import_bg(argv: list[str]) -> int:
    if len(argv) < 2:
        return 0
    tpath = Path(argv[0]).expanduser()
    conv_id = argv[1]
    cwd = argv[2] if len(argv) > 2 else ""
    if not tpath.is_file() or not lmemory_capture.consented():
        return 0
    vault_raw = lmemory_home.vault_path()
    if not vault_raw or not Path(vault_raw).is_dir():
        return 0
    vault = Path(vault_raw).expanduser()

    import_sessions.hold_lock()
    turns = _read_antigravity_turns(tpath)
    if not turns:
        return 0

    import_sessions.PAGE_LANG = zones.lang(vault)
    st = import_sessions.load_state()
    roots_out = list(st.get("exclude_roots") or [])
    folder = zones.path(vault, import_sessions.FOLDER)

    have: dict[tuple[str, str], Path] = {}
    if folder.is_dir():
        for path in folder.glob("*.md"):
            meta = import_sessions.frontmatter(path)
            if meta.get("source") in (import_sessions.MARK, "krouter-import") and meta.get("session"):
                have[(meta["session"], meta.get("date", ""))] = path

    if import_sessions.excluded({"turns": turns, "cwd": cwd, "id": conv_id}, roots_out):
        for (sid, _day), path in have.items():
            if sid == conv_id and path.is_file():
                path.unlink()
        return 0

    fallback_day = datetime.fromtimestamp(tpath.stat().st_mtime).date()
    by_day: dict = {}
    for t in turns:
        day = import_sessions.local_day(t["ts"]) or fallback_day
        by_day.setdefault(day, []).append(t)

    ids, days = import_sessions.daily_coverage(vault)
    overlap = st.get("overlap") or "link"
    root = lmemory_home.project_root(cwd)
    project = Path(cwd).name if cwd else ""

    for day, day_turns in sorted(by_day.items()):
        title = import_sessions.clean(day_turns[0]["ask"], 60).split("\n")[0] or "会话"
        e = {
            "agent": "antigravity",
            "id": conv_id,
            "day": day,
            "turns": day_turns,
            "project": project,
            "root": root,
            "title": title,
            "first_key": import_sessions.turn_key(day_turns[0]),
        }
        e["covered_by"] = import_sessions.covered_by(e, ids, days, {conv_id})
        before = have.get((conv_id, day.isoformat()))
        if overlap == "skip" and e["covered_by"]:
            if before and before.is_file():
                before.unlink()
            continue

        target = folder / import_sessions.file_name(e)
        if target.exists() and import_sessions.frontmatter(target).get("source") not in (import_sessions.MARK, "krouter-import"):
            continue
        if before and before.exists():
            e["superseded_by"] = import_sessions.frontmatter(before).get("superseded_by", "")

        digest = import_sessions.old_digest(before, len(day_turns))
        covers = len(day_turns)
        if not digest:
            prior, done = import_sessions.prior_digest(before, e)
            if prior:
                digest, covers = "\n".join(prior), done

        page = import_sessions.render(e, digest, covers)
        if before and before.exists():
            supplement, protected = import_sessions.saved_supplements(before)
            if protected:
                page = page.replace("---\n", "---\nsecret: true\n", 1)
            if supplement:
                page += "\n" + lmemory_redact.redact(supplement) + "\n"

        folder.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(f"{target.name}.tmp-{os.getpid()}")
        tmp.write_text(page, encoding="utf-8")
        os.replace(tmp, target)
        if before and before != target and before.exists():
            before.unlink()

    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "import-bg":
        try:
            return cmd_import_bg(sys.argv[2:])
        except Exception as exc:  # noqa: BLE001
            print(f"lmemory-agy import-bg: {str(exc)[:200]}", file=sys.stderr)
            return 0
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    try:
        handler = {"start": cmd_start, "prompt": cmd_prompt, "stop": cmd_stop}.get(cmd)
        if handler:
            return handler(payload)
    except Exception as exc:  # noqa: BLE001
        print(f"lmemory-agy {cmd}: {str(exc)[:200]}", file=sys.stderr)
    _out({})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Proving Ground v0.1 — the assistant's monthly self-test.

Monthly, on the first Monday of the month at 9:00 AM CST. Five events, 20 points
each, 100 total. No fudging. No peeking at answer keys. The person taking
the test must not read sealed/ before a live run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

import arc
import bank
import house
import logbook
import memory_quiz
import paths
import range_event
import ranks
import realworld
import replay
import runstate
import schedule
import scoring
import seal
import shootout

PROG = "proving.py"


def _print(text: str) -> int:
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    return 0


def _fail(message: str, code: int = 1) -> int:
    sys.stderr.write(message if message.endswith("\n") else message + "\n")
    return code


def _resolve_run(run_id: str | None, *, kind: str | None = None) -> dict[str, Any]:
    if run_id:
        return runstate.load(run_id)
    current = runstate.latest_in_progress(kind)
    if current:
        return current
    raise RuntimeError("No in-progress run. Start one with: proving.py start   or   proving.py dry-start")


def _read_text(path: str | None, stdin_ok: bool) -> str:
    if path:
        return Path(path).read_text(encoding="utf-8")
    if stdin_ok and not sys.stdin.isatty():
        return sys.stdin.read()
    return ""


def cmd_status(_args: argparse.Namespace) -> int:
    lines = [
        "Proving Ground v0.1",
        paths.now_human(),
        schedule.describe(),
        "",
        bank.bank_info(),
    ]
    reason = house.writes_blocked()
    if reason:
        lines += ["", f"Safe mode: WRITES FROZEN. {reason}"]
    consultant = house.consultant_blocked()
    if consultant and consultant != reason:
        lines += ["", f"Consultant / shootout: {consultant}"]
    current = runstate.latest_in_progress()
    if current:
        missing = runstate.missing_events(current)
        lines += [
            "",
            f"In-progress run: {current['id']} ({current['kind']})",
            f"Started: {current.get('started')}",
            "Events done: " + (", ".join(current.get("events") or {}) or "none"),
            "Still needed: " + (", ".join(missing) or "none — ready to finish"),
        ]
    official = [e for e in logbook.load_entries(True) if e.get("id") == paths.month_id()]
    if official:
        lines += ["", f"Official run for {paths.month_id()} is already on the logbook."]
    last = logbook.load_entries(True)
    if last:
        lines += ["", "Latest official:", logbook.format_entry(last[-1]).rstrip()]
    else:
        lines += ["", "No official runs on the logbook yet."]
    return _print("\n".join(lines))


def cmd_schedule(_args: argparse.Namespace) -> int:
    return _print(schedule.describe())


def cmd_logbook(_args: argparse.Namespace) -> int:
    entries = logbook.load_entries(True)
    if not entries:
        return _print("No official runs on the logbook yet.")
    chunks = [logbook.format_entry(e).rstrip() for e in entries]
    chunks.append("Trends:\n" + logbook.trends_text(entries))
    return _print("\n\n".join(chunks))


def cmd_trends(_args: argparse.Namespace) -> int:
    return _print(logbook.trends_text())


def cmd_replay(args: argparse.Namespace) -> int:
    if args.month:
        path = paths.replay_dir() / f"{args.month}.txt"
        if not path.is_file():
            return _fail(f"No replay clip for {args.month}.")
        return _print(path.read_text(encoding="utf-8"))
    clips = replay.list_clips()
    if not clips:
        return _print("No replay clips yet.")
    return _print("\n---\n".join(c.rstrip() for c in clips))


def cmd_bank_info(_args: argparse.Namespace) -> int:
    return _print(bank.bank_info())


def cmd_rank(args: argparse.Namespace) -> int:
    return _print(ranks.describe(args.total))


def _start(kind: str, run_id: str | None, force: bool, notes: str) -> int:
    house.require_writable()
    stamp = paths.now()
    month = paths.month_id(stamp)
    ident = run_id or (month if kind == "official" else f"dry-{stamp.strftime('%Y%m%d-%H%M%S')}")
    if kind == "official":
        if not schedule.in_window(stamp) and not force:
            opens, _closes = schedule.window_for(stamp)
            if stamp < opens:
                return _fail(
                    f"The official window for {month} is not open yet. "
                    f"{schedule.describe()} Re-run with --force if the owner wants an early start."
                )
        if logbook.has_official(month) and not force:
            return _fail(
                f"An official run for {month} is already on the logbook. "
                "The owner can allow a redo with --force (the old entry stays; the logbook is append-only)."
            )
        if runstate.exists(ident) and runstate.load(ident).get("status") == "complete" and not force:
            return _fail(f"Official run {ident} is already complete.")
        if not run_id:
            ident = month
    run = runstate.create(ident, kind, notes=notes)
    next_steps = (
        f"Started {kind} run {run['id']}.\n"
        "Work the events in any order, then finish:\n"
        f"  python3 {PROG} arc --answers-file FILE\n"
        f"  python3 {PROG} memory --answers-file FILE\n"
        f"  python3 {PROG} realworld --task TEXT --score N --rubric TEXT\n"
        f"  python3 {PROG} shootout prepare --prompt-file P --answer-file A\n"
        f"  python3 {PROG} shootout packet\n"
        f"  python3 {PROG} shootout grade --pick A|B|tie   (or --score N)\n"
        f"  python3 {PROG} shootout reveal\n"
        f"  python3 {PROG} range\n"
        f"  python3 {PROG} finish\n"
        "Do not open sealed/ or ask for solutions before you submit answers."
    )
    return _print(next_steps)


def cmd_start(args: argparse.Namespace) -> int:
    return _start("official", args.run, args.force, args.notes or "")


def cmd_dry_start(args: argparse.Namespace) -> int:
    return _start("dry", args.run, True, args.notes or "")


def _arc_tasks(run: dict[str, Any]) -> list[arc.Task]:
    if run.get("kind") == "official":
        year, month = (int(p) for p in run["id"].split("-")[:2])
        seed = arc.month_seed(year, month)
    else:
        seed = f"pg-arc-dry-{run['id']}"
    return arc.generate(seed)


def cmd_arc(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    tasks = _arc_tasks(run)
    if args.show:
        return _print(arc.present(tasks))
    raw = _read_text(args.answers_file, stdin_ok=not args.show)
    if not raw:
        # Show the puzzles and wait? For non-interactive use, require a file.
        _print(arc.present(tasks))
        return _fail("No answers given. Re-run with --answers-file or pipe the four grids on stdin.")
    try:
        answers = arc.parse_answer_list(raw, len(tasks))
    except ValueError as exc:
        return _fail(str(exc))
    result = arc.grade(tasks, answers)
    runstate.put_event(run, result, creative=args.creative or "")
    return _print(f"ARC event saved for {run['id']}: {result['detail']}, {result['score']:g}/{result['max']}")


def _memory_items(run: dict[str, Any]) -> list[dict[str, Any]]:
    if run.get("kind") == "official":
        year, month = (int(p) for p in run["id"].split("-")[:2])
        return memory_quiz.sample(year, month)
    # Dry runs use a different seed so they do not preview the live monthly set.
    stamp = run["id"]
    year = 1999
    month = 1
    payload = bank.load_bank()
    # Sample with a dry-only seed by temporarily using an off-calendar key.
    import random as _random
    items = list(payload.get("questions") or [])
    rng = _random.Random(f"pg-memory-dry-{stamp}")
    if len(items) < memory_quiz.QUESTIONS_PER_ROUND:
        raise RuntimeError("sealed memory bank does not have enough questions")
    return rng.sample(items, memory_quiz.QUESTIONS_PER_ROUND)


def cmd_memory(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    questions = _memory_items(run)
    if args.show:
        return _print(memory_quiz.present(questions))
    raw = _read_text(args.answers_file, stdin_ok=True)
    if not raw:
        _print(memory_quiz.present(questions))
        return _fail("No answers given. Re-run with --answers-file or pipe answers on stdin.")
    try:
        answers = memory_quiz.parse_answer_list(raw, len(questions))
    except ValueError as exc:
        return _fail(str(exc))
    result = memory_quiz.grade(questions, answers)
    runstate.put_event(run, result, creative=args.creative or "")
    return _print(
        f"Memory event saved for {run['id']}: {result['detail']}, {result['score']:g}/{result['max']}"
    )


def cmd_realworld(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    try:
        result = realworld.record(
            args.task, args.score, rubric=args.rubric or "", creative=args.creative or "", notes=args.notes or ""
        )
    except ValueError as exc:
        return _fail(str(exc))
    runstate.put_event(run, result)
    return _print(f"Real-world event saved for {run['id']}: {result['detail']}")


def cmd_range(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    result = range_event.record()
    runstate.put_event(run, result, creative=args.creative or "")
    return _print(f"Range event saved for {run['id']}: {result['detail']}")


def _shootout_paths(run_id: str) -> dict[str, Path]:
    root = paths.run_dir(run_id)
    return {
        "packet": root / "shootout-blind.md",
        "seal": root / "shootout-map.seal",
        "grade": root / "shootout-grade.json",
        "revealed": root / "shootout-revealed.flag",
    }


def cmd_shootout_prepare(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    prompt = (args.prompt or "").strip() or _read_text(args.prompt_file, stdin_ok=False).strip()
    answer = (args.answer or "").strip() or _read_text(args.answer_file, stdin_ok=False).strip()
    mock = args.stock if args.stock is not None else None
    try:
        prepared = shootout.prepare(
            run["id"],
            prompt,
            answer,
            stock_answer=mock,
            model=args.model,
        )
    except (RuntimeError, ValueError) as exc:
        return _fail(str(exc))
    house.require_writable()
    files = _shootout_paths(run["id"])
    paths.safe_write(files["packet"], prepared["packet"])
    paths.safe_write(files["seal"], prepared["sealed_mapping"] + "\n")
    if files["revealed"].exists():
        files["revealed"].unlink()
    if files["grade"].exists():
        files["grade"].unlink()
    return _print(
        f"Shootout packet is ready for {run['id']}.\n"
        f"Show the owner the unlabeled pair with: python3 {PROG} shootout packet\n"
        "Do not reveal who is A or B until after he grades."
    )


def cmd_shootout_packet(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    packet = _shootout_paths(run["id"])["packet"]
    if not packet.is_file():
        return _fail("No shootout packet yet. Run: proving.py shootout prepare ...")
    return _print(packet.read_text(encoding="utf-8"))


def _load_mapping(run_id: str) -> dict[str, Any]:
    path = _shootout_paths(run_id)["seal"]
    if not path.is_file():
        raise FileNotFoundError("No sealed shootout map. Run shootout prepare first.")
    return shootout.decode_mapping(path.read_text(encoding="utf-8").strip())


def cmd_shootout_grade(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    try:
        mapping = _load_mapping(run["id"])
        result = shootout.grade(
            mapping, pick=args.pick, score=args.score, notes=args.notes or "", creative=args.creative or ""
        )
    except (ValueError, FileNotFoundError, Exception) as exc:
        return _fail(str(exc))
    house.require_writable()
    paths.safe_write(_shootout_paths(run["id"])["grade"], json.dumps(result, indent=2, sort_keys=True) + "\n")
    # Store the score, but keep assistant_was off the run file until reveal so a mid-run status
    # peek cannot spoil the blind grade. The grade file holds the full result.
    slim = {
        "event": "shootout",
        "score": result["score"],
        "max": result["max"],
        "pick": result.get("pick"),
        "source": result.get("source"),
        "notes": result.get("notes"),
        "creative": result.get("creative"),
        "detail": f"graded ({result.get('source')}); reveal to record the letters",
        "model": result.get("model"),
        "revealed": False,
    }
    runstate.put_event(run, slim)
    return _print(
        f"Shootout grade saved for {run['id']}: {result['score']:g}/{result['max']}. "
        f"Reveal with: python3 {PROG} shootout reveal"
    )


def cmd_shootout_reveal(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    files = _shootout_paths(run["id"])
    if not files["grade"].is_file():
        return _fail("Reveal is after the grade, not before. The owner grades first.")
    try:
        mapping = _load_mapping(run["id"])
    except Exception as exc:
        return _fail(str(exc))
    result = json.loads(files["grade"].read_text(encoding="utf-8"))
    text = shootout.reveal_text(mapping, result)
    result["revealed"] = True
    result["detail"] = shootout._detail(result["score"], result.get("source") or "", result.get("assistant_was"))
    house.require_writable()
    paths.safe_write(files["grade"], json.dumps(result, indent=2, sort_keys=True) + "\n")
    paths.safe_write(files["revealed"], "revealed\n")
    runstate.put_event(run, result, creative=result.get("creative") or "")
    return _print(text)


def cmd_finish(args: argparse.Namespace) -> int:
    run = _resolve_run(args.run)
    missing = runstate.missing_events(run)
    if missing:
        return _fail("Cannot finish yet. Still needed: " + ", ".join(missing))
    # Shootout must be revealed so the official record is complete.
    shoot = (run.get("events") or {}).get("shootout") or {}
    if shoot and not shoot.get("revealed") and shoot.get("source"):
        return _fail("Reveal the shootout before finishing so the official record is complete.")
    ev = run["events"]
    scores = {eid: ev[eid]["score"] for eid in scoring.EVENT_IDS}
    total = scoring.total_of(scores)
    patch = ranks.rank(total)
    run["total"] = total
    run["rank"] = patch
    run["status"] = "complete"
    run["finished"] = paths.now_iso()
    if args.notes:
        run["notes"] = ((run.get("notes") or "") + " " + args.notes).strip()
    entry = {
        "id": run["id"] if run["kind"] == "official" else f"dry:{run['id']}",
        "month": paths.month_id(),
        "kind": run["kind"],
        "time": run["finished"],
        "timezone": paths.TZ_LABEL,
        "events": ev,
        "total": total,
        "rank": patch,
        "notes": run.get("notes") or "",
        "started": run.get("started"),
    }
    if run["kind"] == "official":
        logbook.append({**entry, "kind": "official", "id": run["id"]})
        clip_path = replay.write_clip(entry)
        run["replay"] = str(clip_path)
        runstate.save(run)
        return _print(
            logbook.format_entry(entry)
            + f"\nRank patch: {patch}\n"
            + f"Logbook updated. Replay clip: {clip_path}\n"
        )
    # Dry run: write a local summary and a clip under the run folder only, never the official logbook.
    house.require_writable()
    summary = paths.run_dir(run["id"]) / "dry-summary.md"
    clip = replay.clip_for(entry)
    paths.safe_write(summary, logbook.format_entry(entry) + "\n" + clip)
    paths.safe_write(paths.run_dir(run["id"]) / "dry-clip.txt", clip)
    run["replay"] = str(paths.run_dir(run["id"]) / "dry-clip.txt")
    runstate.save(run)
    return _print(
        logbook.format_entry(entry)
        + "\nThis was a DRY RUN. It was not written to the official logbook.\n"
        + f"Sandbox summary: {summary}\n"
    )


def cmd_dry_run(args: argparse.Namespace) -> int:
    """One-shot sandbox: start, apply dummy answers, finish, do not record officially."""
    ident = args.run or f"dry-{paths.now().strftime('%Y%m%d-%H%M%S')}"
    start_ns = argparse.Namespace(run=ident, notes=args.notes or "sandbox dry-run", force=True)
    code = cmd_dry_start(start_ns)
    if code != 0:
        return code
    # ARC
    if args.arc_answers:
        code = cmd_arc(argparse.Namespace(run=ident, answers_file=args.arc_answers, show=False, creative=args.creative or ""))
        if code != 0:
            return code
    else:
        return _fail("dry-run needs --arc-answers")
    if args.memory_answers:
        code = cmd_memory(argparse.Namespace(run=ident, answers_file=args.memory_answers, show=False, creative=""))
        if code != 0:
            return code
    else:
        return _fail("dry-run needs --memory-answers")
    code = cmd_realworld(
        argparse.Namespace(
            run=ident,
            task=args.task,
            score=args.score,
            rubric=args.rubric or "",
            creative="",
            notes="",
        )
    )
    if code != 0:
        return code
    if not args.shootout_prompt_file and not args.shootout_prompt:
        return _fail("dry-run needs --shootout-prompt-file (or --shootout-prompt) and --shootout-answer-file")
    code = cmd_shootout_prepare(
        argparse.Namespace(
            run=ident,
            prompt=args.shootout_prompt,
            prompt_file=args.shootout_prompt_file,
            answer=None,
            answer_file=args.shootout_answer_file,
            stock=args.shootout_mock,
            model=shootout.DEFAULT_MODEL,
        )
    )
    if code != 0:
        return code
    code = cmd_shootout_grade(
        argparse.Namespace(
            run=ident,
            pick=args.shootout_pick,
            score=args.shootout_score,
            notes="",
            creative="",
        )
    )
    if code != 0:
        return code
    code = cmd_shootout_reveal(argparse.Namespace(run=ident))
    if code != 0:
        return code
    code = cmd_range(argparse.Namespace(run=ident, creative=""))
    if code != 0:
        return code
    return cmd_finish(argparse.Namespace(run=ident, notes=""))


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog=PROG,
        description="An assistant's monthly Proving Ground. No peeking, no fudging, no destruction.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Window, safe mode, in-progress run, last official result")
    sub.add_parser("schedule", help="When the official monthly window opens")
    sub.add_parser("logbook", help="Print official runs")
    sub.add_parser("trends", help="Per-event trends over official runs")
    rp = sub.add_parser("replay", help="Show Moot projector clips")
    rp.add_argument("--month", help="Month id like 2026-11")
    sub.add_parser("bank-info", help="Sealed bank status only (no questions)")
    rk = sub.add_parser("rank", help="Show the patch for a total")
    rk.add_argument("--total", type=float, required=True)

    st = sub.add_parser("start", help="Open this month's official run")
    st.add_argument("--run", help="Override run id (default: YYYY-MM)")
    st.add_argument("--force", action="store_true", help="The owner override: early, late, or a second run")
    st.add_argument("--notes", default="")

    ds = sub.add_parser("dry-start", help="Open a sandbox run that will not touch the official logbook")
    ds.add_argument("--run", help="Override run id")
    ds.add_argument("--notes", default="")

    def add_run(cmd, creative=True):
        cmd.add_argument("--run", help="Run id (default: the in-progress run)")
        if creative:
            cmd.add_argument("--creative", default="", help="Creative-solutions note (does not change the score)")

    a = sub.add_parser("arc", help="Show or grade the mini ARC round")
    add_run(a)
    a.add_argument("--answers-file", help="File with the four test output grids")
    a.add_argument("--show", action="store_true", help="Print the puzzles without grading")

    m = sub.add_parser("memory", help="Show or grade the memory & continuity quiz")
    add_run(m)
    m.add_argument("--answers-file")
    m.add_argument("--show", action="store_true")

    rw = sub.add_parser("realworld", help="Record the owner's real-world task and their score")
    add_run(rw)
    rw.add_argument("--task", required=True, help="The chore the owner picked this month")
    rw.add_argument("--score", type=float, required=True, help="The owner's score, 0-20")
    rw.add_argument("--rubric", default="")
    rw.add_argument("--notes", default="")

    rg = sub.add_parser("range", help="Pull the latest range qual and scale 40 -> 20")
    add_run(rg)

    sh = sub.add_parser("shootout", help="Blind shootout vs a stock model via Consultant")
    sh_sub = sh.add_subparsers(dest="shootout_cmd", required=True)
    prep = sh_sub.add_parser("prepare", help="Send the public prompt to Consultant and shuffle A/B")
    add_run(prep, creative=False)
    prep.add_argument("--prompt", default="")
    prep.add_argument("--prompt-file")
    prep.add_argument("--answer", default="")
    prep.add_argument("--answer-file")
    prep.add_argument("--stock", default=None, help="Optional canned stock answer (tests / no-network dry run)")
    prep.add_argument("--model", default=shootout.DEFAULT_MODEL)
    packet = sh_sub.add_parser("packet", help="Print the unlabeled A/B packet for the owner")
    add_run(packet, creative=False)
    grade = sh_sub.add_parser("grade", help="The owner's blind grade")
    add_run(grade)
    grade.add_argument("--pick", choices=("A", "B", "a", "b", "tie", "TIE", "Tie"))
    grade.add_argument("--score", type=float)
    grade.add_argument("--notes", default="")
    rev = sh_sub.add_parser("reveal", help="Show who was A and B, after the grade")
    add_run(rev, creative=False)

    fin = sub.add_parser("finish", help="Close the run, write the logbook (official only) and a replay clip")
    fin.add_argument("--run")
    fin.add_argument("--notes", default="")

    dry = sub.add_parser("dry-run", help="One-shot sandbox with dummy answers; not an official run")
    dry.add_argument("--run")
    dry.add_argument("--notes", default="")
    dry.add_argument("--arc-answers", required=True)
    dry.add_argument("--memory-answers", required=True)
    dry.add_argument("--task", required=True)
    dry.add_argument("--score", type=float, required=True)
    dry.add_argument("--rubric", default="")
    dry.add_argument("--shootout-prompt", default="")
    dry.add_argument("--shootout-prompt-file")
    dry.add_argument("--shootout-answer-file", required=True)
    dry.add_argument("--shootout-mock", default="This is a canned stock-model answer for a sandbox dry run.")
    dry.add_argument("--shootout-pick", default="A")
    dry.add_argument("--shootout-score", type=float, default=None)
    dry.add_argument("--creative", default="")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            return cmd_status(args)
        if args.command == "schedule":
            return cmd_schedule(args)
        if args.command == "logbook":
            return cmd_logbook(args)
        if args.command == "trends":
            return cmd_trends(args)
        if args.command == "replay":
            return cmd_replay(args)
        if args.command == "bank-info":
            return cmd_bank_info(args)
        if args.command == "rank":
            return cmd_rank(args)
        if args.command == "start":
            return cmd_start(args)
        if args.command == "dry-start":
            return cmd_dry_start(args)
        if args.command == "arc":
            return cmd_arc(args)
        if args.command == "memory":
            return cmd_memory(args)
        if args.command == "realworld":
            return cmd_realworld(args)
        if args.command == "range":
            return cmd_range(args)
        if args.command == "shootout":
            if args.shootout_cmd == "prepare":
                return cmd_shootout_prepare(args)
            if args.shootout_cmd == "packet":
                return cmd_shootout_packet(args)
            if args.shootout_cmd == "grade":
                return cmd_shootout_grade(args)
            if args.shootout_cmd == "reveal":
                return cmd_shootout_reveal(args)
        if args.command == "finish":
            return cmd_finish(args)
        if args.command == "dry-run":
            return cmd_dry_run(args)
        return _fail("unknown command")
    except (RuntimeError, FileNotFoundError, ValueError, paths.WriteOutsideData) as exc:
        return _fail(str(exc))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Procedural mini ARC-style grid puzzles.

A month seed picks four tasks (20 points, 5 each). Solutions are computed
from the same seed at grade time and are never printed by the CLI unless
PROVING_ALLOW_PEEK=1 (tests only). New puzzles exist each month.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Sequence

import scoring

Grid = tuple[tuple[int, ...], ...]
POINTS_EACH = 5
TASKS_PER_ROUND = 4
MAX_COLOR = 9


def make_grid(rows: Sequence[Sequence[int]]) -> Grid:
    return tuple(tuple(int(c) for c in row) for row in rows)


def grid_equal(a: Grid, b: Grid) -> bool:
    return a == b


def render_grid(grid: Grid) -> str:
    return "\n".join(" ".join(str(c) for c in row) for row in grid)


def parse_grid(text: str) -> Grid:
    rows: list[tuple[int, ...]] = []
    for raw in (text or "").strip().splitlines():
        line = raw.strip()
        if not line or set(line) <= set("-"):
            continue
        line = line.replace(",", " ").replace(";", " ")
        parts = [p for p in re.split(r"\s+", line) if p != ""]
        if not parts:
            continue
        try:
            rows.append(tuple(int(p) for p in parts))
        except ValueError as exc:
            raise ValueError(f"grid cells must be integers 0-9: {line!r}") from exc
        if any(c < 0 or c > MAX_COLOR for c in rows[-1]):
            raise ValueError(f"grid cells must be 0-9: {line!r}")
    if not rows:
        raise ValueError("empty grid")
    width = len(rows[0])
    if any(len(r) != width for r in rows):
        raise ValueError("ragged grid")
    return tuple(rows)


def parse_answer_list(text: str, expected: int) -> list[Grid]:
    """Grids separated by a blank line, a --- line, or a 'Q n:' header."""
    chunk = (text or "").replace("\r\n", "\n").strip()
    if not chunk:
        raise ValueError("no answers provided")
    # Allow one-line form: 1 0; 0 1  //  2 2; 2 2
    if "//" in chunk and "\n\n" not in chunk:
        parts = [p.strip() for p in chunk.split("//")]
        return [parse_grid(p.replace(";", "\n")) for p in parts if p]
    blocks: list[str] = []
    current: list[str] = []
    for raw in chunk.splitlines():
        line = raw.strip()
        if re.match(r"^q\s*\d+\s*:", line, re.I):
            if current:
                blocks.append("\n".join(current))
                current = []
            line = re.sub(r"^q\s*\d+\s*:", "", line, flags=re.I).strip()
            if line:
                current.append(line.replace(";", "\n"))
            continue
        if line == "" or set(line) <= set("-"):
            if current:
                blocks.append("\n".join(current))
                current = []
            continue
        current.append(line.replace(";", "\n") if ";" in line else line)
    if current:
        blocks.append("\n".join(current))
    grids = [parse_grid(b.replace(";", "\n")) for b in blocks]
    if len(grids) != expected:
        raise ValueError(f"expected {expected} grids, got {len(grids)}")
    return grids


def _rotate90(grid: Grid) -> Grid:
    return make_grid(list(zip(*grid[::-1])))


def _rotate180(grid: Grid) -> Grid:
    return _rotate90(_rotate90(grid))


def _flip_h(grid: Grid) -> Grid:
    return make_grid([row[::-1] for row in grid])


def _flip_v(grid: Grid) -> Grid:
    return make_grid(grid[::-1])


def _transpose(grid: Grid) -> Grid:
    return make_grid(list(zip(*grid)))


def _recolor(grid: Grid, mapping: dict[int, int]) -> Grid:
    return make_grid([[mapping.get(c, c) for c in row] for row in grid])


def _gravity(grid: Grid) -> Grid:
    h, w = len(grid), len(grid[0])
    out = [[0] * w for _ in range(h)]
    for x in range(w):
        stack = [grid[y][x] for y in range(h) if grid[y][x] != 0]
        y = h - 1
        for val in reversed(stack):
            out[y][x] = val
            y -= 1
    return make_grid(out)


def _tile2(grid: Grid) -> Grid:
    # 2x2 tiling of the input.
    rows: list[list[int]] = []
    for row in grid:
        rows.append(list(row) + list(row))
    return make_grid(rows + rows)


def _bbox(grid: Grid) -> Grid:
    cells = [(y, x) for y, row in enumerate(grid) for x, c in enumerate(row) if c != 0]
    if not cells:
        return make_grid([[0]])
    ys = [y for y, _ in cells]
    xs = [x for _, x in cells]
    return make_grid([row[min(xs) : max(xs) + 1] for row in grid[min(ys) : max(ys) + 1]])


def _cycle(grid: Grid, shift: int, colors: int) -> Grid:
    def nxt(c: int) -> int:
        if c == 0:
            return 0
        return ((c - 1 + shift) % colors) + 1

    return make_grid([[nxt(c) for c in row] for row in grid])


def _halves_or(grid: Grid) -> Grid:
    w = len(grid[0])
    mid = w // 2
    out = []
    for row in grid:
        left, right = row[:mid], row[mid : mid + mid]
        if len(right) < len(left):
            right = right + (0,) * (len(left) - len(right))
        out.append(tuple(a if a else b for a, b in zip(left, right)))
    return make_grid(out)


def _rand_grid(rng: random.Random, h: int, w: int, colors: int, fill: float = 0.55) -> Grid:
    rows = []
    for _ in range(h):
        rows.append([rng.randint(1, colors) if rng.random() < fill else 0 for _ in range(w)])
    # Guarantee at least one non-zero so bbox/gravity stay interesting.
    if all(c == 0 for row in rows for c in row):
        rows[rng.randint(0, h - 1)][rng.randint(0, w - 1)] = rng.randint(1, colors)
    return make_grid(rows)


@dataclass(frozen=True)
class Example:
    inp: Grid
    out: Grid


@dataclass
class Task:
    task_id: str
    title: str
    rule_hint: str
    train: list[Example]
    test_input: Grid
    test_output: Grid = field(repr=False)
    points: int = POINTS_EACH

    def prompt(self) -> str:
        lines = [f"{self.task_id}. {self.title}", self.rule_hint, ""]
        for i, ex in enumerate(self.train, 1):
            lines.append(f"Example {i} input:")
            lines.append(render_grid(ex.inp))
            lines.append(f"Example {i} output:")
            lines.append(render_grid(ex.out))
            lines.append("")
        lines.append("Test input:")
        lines.append(render_grid(self.test_input))
        lines.append("Write the test output grid.")
        return "\n".join(lines)


def _apply(kind: str, grid: Grid, params: dict) -> Grid:
    if kind == "rotate90":
        return _rotate90(grid)
    if kind == "rotate180":
        return _rotate180(grid)
    if kind == "flip_h":
        return _flip_h(grid)
    if kind == "flip_v":
        return _flip_v(grid)
    if kind == "transpose":
        return _transpose(grid)
    if kind == "recolor":
        return _recolor(grid, params["map"])
    if kind == "gravity":
        return _gravity(grid)
    if kind == "tile2":
        return _tile2(grid)
    if kind == "bbox":
        return _bbox(grid)
    if kind == "cycle":
        return _cycle(grid, params["shift"], params["colors"])
    if kind == "halves_or":
        return _halves_or(grid)
    raise ValueError(kind)


# Public titles only — they describe the format, not the hidden rule.
# The rule is shown only through the worked examples, like ARC.
_KINDS = (
    ("rotate90", "Turn the pattern", "Study the examples, then apply the same change."),
    ("rotate180", "Turn the pattern", "Study the examples, then apply the same change."),
    ("flip_h", "Mirror the pattern", "Study the examples, then apply the same change."),
    ("flip_v", "Mirror the pattern", "Study the examples, then apply the same change."),
    ("transpose", "Rewrite the pattern", "Study the examples, then apply the same change."),
    ("recolor", "Repaint the pattern", "Study the examples, then apply the same change."),
    ("gravity", "Restack the pattern", "Study the examples, then apply the same change."),
    ("tile2", "Grow the pattern", "Study the examples, then apply the same change."),
    ("bbox", "Crop the pattern", "Study the examples, then apply the same change."),
    ("cycle", "Shift the paints", "Study the examples, then apply the same change."),
    ("halves_or", "Fold the pattern", "Study the examples, then apply the same change."),
)


def _params(kind: str, rng: random.Random, colors: int) -> dict:
    if kind == "recolor":
        src = list(range(1, colors + 1))
        dst = src[:]
        rng.shuffle(dst)
        # Keep 0 as 0; ensure it's not a no-op.
        if dst == src:
            dst[0], dst[-1] = dst[-1], dst[0]
        return {"map": {0: 0, **dict(zip(src, dst))}}
    if kind == "cycle":
        shift = rng.choice([1, 2, 3])
        return {"shift": shift, "colors": colors}
    return {}


def _sized(kind: str, rng: random.Random) -> tuple[int, int, int]:
    colors = rng.choice([3, 4, 5])
    if kind == "tile2":
        return rng.choice([2, 3]), rng.choice([2, 3]), colors
    if kind == "halves_or":
        w = rng.choice([4, 6])
        return rng.choice([3, 4]), w, colors
    if kind == "bbox":
        return rng.choice([4, 5]), rng.choice([4, 5]), colors
    return rng.choice([3, 4]), rng.choice([3, 4]), colors


def _one_task(rng: random.Random, kind: str, title: str, hint: str, tag: str) -> Task:
    h, w, colors = _sized(kind, rng)
    params = _params(kind, rng, colors)
    fill = 0.7 if kind in {"bbox", "gravity", "halves_or"} else 0.55
    train: list[Example] = []
    for _ in range(2):
        inp = _rand_grid(rng, h, w, colors, fill=fill)
        if kind == "bbox":
            # Leave a zero margin so the crop is visible.
            margin = [list(r) for r in inp]
            for x in range(w):
                margin[0][x] = 0
                margin[-1][x] = 0
            for y in range(h):
                margin[y][0] = 0
                margin[y][-1] = 0
            inp = make_grid(margin)
        train.append(Example(inp, _apply(kind, inp, params)))
    test_in = _rand_grid(rng, h, w, colors, fill=fill)
    if kind == "bbox":
        margin = [list(r) for r in test_in]
        for x in range(w):
            margin[0][x] = 0
            margin[-1][x] = 0
        for y in range(h):
            margin[y][0] = 0
            margin[y][-1] = 0
        test_in = make_grid(margin)
    test_out = _apply(kind, test_in, params)
    return Task(tag, title, hint, train, test_in, test_out)


def month_seed(year: int, month: int) -> str:
    return f"pg-arc-v1-{year:04d}-{month:02d}"


def generate(seed: str, count: int = TASKS_PER_ROUND) -> list[Task]:
    rng = random.Random(seed)
    kinds = list(_KINDS)
    rng.shuffle(kinds)
    picked = kinds[:count]
    tasks: list[Task] = []
    for i, (kind, title, hint) in enumerate(picked, 1):
        tasks.append(_one_task(rng, kind, title, hint, f"A{i}"))
    return tasks


def present(tasks: Sequence[Task]) -> str:
    parts = [
        "Mini ARC round — four grid tasks, 5 points each, 20 points total.",
        "Each task shows two worked examples and one test input.",
        "Submit the four test output grids (blank line or --- between them).",
        "No peeking at the key. Exact grid match only; no partial credit per task.",
        "",
    ]
    for task in tasks:
        parts.append(task.prompt())
        parts.append("")
        parts.append("---")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def grade(tasks: Sequence[Task], answers: Sequence[Grid]) -> dict:
    results = []
    correct = 0
    for i, task in enumerate(tasks):
        got = answers[i] if i < len(answers) else None
        ok = got is not None and grid_equal(got, task.test_output)
        if ok:
            correct += 1
        results.append({"id": task.task_id, "ok": ok, "points": task.points if ok else 0})
    score = scoring.per_item_score(correct, len(tasks), scoring.EVENT_MAX)
    return {
        "event": "arc",
        "correct": correct,
        "items": len(tasks),
        "score": score,
        "max": scoring.EVENT_MAX,
        "detail": f"{correct}/{len(tasks)} tasks",
        "per_task": results,
    }

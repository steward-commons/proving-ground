# Proving Ground v0.1

A monthly self-test for an AI assistant. Five events, 20 points each, 100 total. The official window opens on the first Monday of the month at 9:00 AM (America/Chicago by default; see `schedule.py`) and stays open through the end of the month. Full effort, no destruction, safety first.

Creative solutions are logged in their own column. They never change a score. There is no edit command and no answer-key peek.

## Rank patches

- below 60: Unqualified
- 60: Marksman
- 75: Sharpshooter
- 90 or above: Expert

## The five events

1. **Mini ARC** — four procedural grid tasks, new each month from a month seed. Exact match, 5 points each.
2. **Memory & continuity** — ten questions sampled from **your own** sealed bank. Hashed answers only.
3. **Real-world task** — the human picks a fresh chore and scores it 0–20 with an optional rubric.
4. **Blind shootout** — a public prompt only. The assistant answers, a stock model answers (through the [gemini-consultant](https://github.com/steward-commons/gemini-consultant) CLI, or a mock), the two are shuffled as A/B, the human grades blind, then reveal.
5. **Range defense** — the latest completed qualification from a range scoreboard (see [the-range](https://github.com/steward-commons/the-range)), scaled 40 → 20.

## Anti-peeking

Your question bank and shootout identity maps live under `sealed/`. **Do not open `sealed/` before a live run.** The CLI shows questions when an event actually starts. Solutions are not printed. This repo ships no bank, no key, and no results; build your own bank from your own memory facts with `bank.py`. Tests use their own temporary banks.

## Safety

- No destruction. The range scoreboard is read, never rewritten.
- No network except the stock-model call on the shootout (public prompts only), and none at all with `PROVING_CONSULTANT=off` or a mock.
- An optional medical guard (safe mode or a `proving` / `consultant` tourniquet) freezes writes or the stock-model call. `status` still works.
- Shootout prompts are scanned for private markers and prompt-injection hits first.

## CLI

```
python3 proving.py status | schedule | logbook | trends | replay | bank-info
python3 proving.py start [--force]
python3 proving.py arc --show
python3 proving.py arc --answers-file arc-answers.txt
python3 proving.py memory --show
python3 proving.py memory --answers-file memory-answers.txt
python3 proving.py realworld --task "the chore" --score 16 --rubric "what was graded" --creative "optional note"
python3 proving.py shootout prepare --prompt-file prompt.txt --answer-file my-answer.txt
python3 proving.py shootout packet
python3 proving.py shootout grade --pick A        # or B, tie, or --score 0-20
python3 proving.py shootout reveal
python3 proving.py range
python3 proving.py finish
```

A sandbox `dry-run` writes a summary under `data/runs/<id>/` and never touches the logbook. The logbook is append-only.

## Environment

See the docstring in `paths.py`: `PROVING_DATA`, `PROVING_SEALED`, `PROVING_RANGE_SCOREBOARD`, `PROVING_CONSULTANT` (path to `consultant.py`, or `off`), `PROVING_CONSULTANT_MOCK`, `PROVING_MEDICAL_GUARD`, `PROVING_DEFENSE_SCAN`, `PROVING_PRIVACY`.

## Tests

```
python3 -m unittest discover -s tests
```

`tests/fixtures/medical_guard.py` is a copy of the guard from the [medical](https://github.com/steward-commons/medical) repo so tests run standalone.

## License

MIT. See `LICENSE`.

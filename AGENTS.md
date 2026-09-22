# polyglot-bench

Benchmark of ten conformance-verified implementations of one database-bound
business transaction across TypeScript, Go and Rust.

## Linear

| | |
|---|---|
| Initiative | [Polyglot Bench](https://linear.app/hallelx2/initiative/polyglot-bench-7352231d7471) — `I-16` |
| Project | [Polyglot Bench — Data Layer Study](https://linear.app/hallelx2/project/polyglot-bench-data-layer-study-77398f7c65c5) — `P-HAL-88` |
| Team | Hallelx2 (`HAL`) |
| Repo | `hallelx2/polyglot-bench` (public, MIT) |

Phase 1 (ten stacks, 450 runs, Friedman/Nemenyi, LaTeX report) is shipped and
lives on `main`. Phase 2 is the data-layer study above.

## Rules specific to this repo

**No number in a document is typed by hand.** `analysis/stats.py` reads the run
files; `analysis/write_docs.py`, `analysis/write_paper.py` and
`analysis/figures.py` read its output. Change a number by re-running the
pipeline, never by editing `README.md`, `RESULTS.md` or `paper/main.tex` —
those are generated.

**Conformance before timing.** `bench/verify.py` must pass before any
measurement is trusted. Output equality is not enough on its own:
`bench/count_statements.sh` checks that variants ask the database the same
questions, which is how GORM's extra `Preload` query was caught.

**Phase-1 results are immutable.** `results/` holds the published 450-run
dataset. New experiments write to `results/<experiment>/`.

**Machine preparation needs explicit consent each time.** Trustworthy runs
require stopping the user's other containers and setting the CPU governor to
`performance`. Ask before each run; restore with `bench/restore-machine.sh`.

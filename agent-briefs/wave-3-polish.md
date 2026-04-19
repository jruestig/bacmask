# Wave 3 — Polish: Benchmarks, Docs, Session Close

Runs after wave 2 merges. Small, mostly mechanical. Can be inlined by
the orchestrator if spawning a dedicated subagent feels heavy.

---

You are finishing the 030 refactor of BacMask
(`/home/jruestig/pro/python/bacmask`). Wave 2 has landed; the tree is now
polygon-canonical. This wave records the measured deltas, syncs the
project documents, and writes the session-close summary.

Read
[knowledge/030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md)
for the doctrine and the baseline table format.

## Preconditions

1. `git status` clean.
2. `uv run pytest` green.
3. `uv run ruff check` + `uv run ruff format --check` clean.
4. `grep -rn "region_masks\|region_areas" bacmask/ tests/` returns zero
   hits.
5. `scripts/bench_polygon_refactor.py` exists (landed in wave 0).

If any precondition fails, report and wait for instructions.

## Task

### 1. Re-run the benchmark harness

```
uv run python scripts/bench_polygon_refactor.py
```

Capture the full output. Run it three times and record the median
per step — a single run is noisy, especially for sub-millisecond
measurements. Use the same fixture image that wave 0 used (the script
already pins it).

### 2. Fill in the post-refactor column of the baseline table

Open `knowledge/030-polygons-are-mask-truth.md`. Find the "Pre-refactor
baseline (wave 0)" section. Fill in the `Post-refactor (ms)` and `Delta`
columns with the medians you measured. Format the delta as either a
percentage (`-42%`, `+3%`) or a ratio (`3.1× faster`, `1.2× slower`),
whichever is clearer for that row.

Add one short paragraph underneath the table titled "**Notes on the
measurements**":

- Call out the memory-footprint delta (~40× less RAM for per-region
  state at N=100 on a 2 MP image — the actual win of this refactor).
  Mention that the wall-clock numbers are a wash because session 7
  already fixed the real cliffs; this wasn't a speedup pass.
- If any step got materially slower (>25%), call it out and explain why.
  Most likely candidate: `compute_area_rows` at large N, if shoelace
  happens to lose to a dict lookup on the test fixture. If so, note
  that it is still sub-millisecond and the tradeoff is worth the
  structural win.

### 3. Update the "What this deletes from the codebase" section of 030

Find that section (it lives near the end of 030). It currently has
"approximate scope" numbers for the expected line reductions. Replace
those estimates with the actual measured deltas from wave 2's final
report. Format:

```
- `core/masking.py` ~310 → NNN lines (−MMM)
- `core/commands.py` ~249 → NNN lines (−MMM)
- `services/mask_service.py` ~674 → NNN lines (−MMM)
```

Use `wc -l` to measure. If the actual numbers differ materially from
the estimates (>20% in either direction), note the reason in a
parenthetical.

### 4. Update _status.md

File: `knowledge/_status.md`.

Move the "Polygon-canonical refactor (knowledge only — code pending)"
entry out of "Currently working on" and into "Recently completed (last
~3 sessions)". Replace its text with a session-close summary:

- Waves completed (0, 1 A/B/C, 2, 3).
- One-line per wave of what it delivered.
- The measured memory-footprint reduction.
- The measured wall-clock deltas (summary — "all operations stayed
  within 20% of baseline; load_bundle got 2× faster; undo snapshot
  memory dropped 100×" or similar, with real numbers).
- The CSV `area_px` shift (numbers changed slightly; now mathematically
  correct shoelace values).
- Link to 030.

Also update "Next actions (concrete, ordered)":

- Remove the "Implement the 030 refactor" item (item 1 today).
- Promote remaining items up by one.

### 5. Update CLAUDE.md Definition of Done if needed

File: `CLAUDE.md`.

Scan the Definition of Done section. The refactor shouldn't change what
the app does, so the checkboxes likely all remain true. But verify:

- Does "User can trace a closed boundary" still work? Yes — lasso is
  unchanged in behavior.
- Does "Bundle can be reloaded" still work? Yes — bundle format
  unchanged.
- Does "CSV is directly human-readable" still hold? Yes — column
  schema unchanged; only `area_px` numbers shifted.

If everything still holds, leave DoD untouched. If anything changed that
affects a checkbox, update it.

One other CLAUDE.md touch: if the "Tech Stack" or "Core Concepts" section
says anything about per-region stored masks, verify it now describes
polygons-canonical accurately. Most likely it already does (session 8
knowledge work covered this) — confirm.

### 6. Final doc scan

Grep the knowledge base for any remaining mentions of `region_masks` or
`region_areas` outside of superseded notes:

```
grep -rn "region_masks\|region_areas" knowledge/ --include="*.md" | grep -v superseded/
```

The only expected hits are in 002 (the "What this state does NOT hold"
section mentions them historically) and 030 (the doctrine itself names
them). Anything else is doc rot — fix or flag.

## Exit criteria

- Benchmark table in 030 fully populated.
- 030's "deletes from codebase" section has actual measured numbers.
- `_status.md` shows the refactor as completed, with numbers.
- `CLAUDE.md` scanned, updates made if needed.
- No non-superseded knowledge note refers to `region_masks` /
  `region_areas` as live state.
- One or two commits depending on how the doc touches group cleanly:
  - `docs(knowledge): fill in 030 post-refactor benchmark numbers`
  - `docs(status): close session — 030 refactor complete`

## Report

One paragraph: the headline numbers (memory delta, any notable
wall-clock changes), whether CLAUDE.md needed updates, anything a
future reader of the knowledge base should know.

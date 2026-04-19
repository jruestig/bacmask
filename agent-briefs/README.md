# Agent Briefs — 030 Refactor

Self-contained prompts for spawning subagent sessions that implement the
[030 — Polygons Are the Only Mask Truth](../knowledge/030-polygons-are-mask-truth.md)
refactor. Each file is a complete prompt: paste it as the `prompt` arg of an
Agent call (or open as a fresh Claude Code session on its own worktree).

## Orchestration

```
Wave 0 ──┐
         ├─ Wave 1 (A ∥ B ∥ C) ──┐
         │                       ├─ Wave 2 (D) ── Wave 3 (E)
         │                       │
         └─ branches cut from ───┘
            post-wave-0 main
```

- **Wave 0** lands first on `master`. All later waves cut their branches from
  post-wave-0 `master`.
- **Wave 1** sessions A, B, C run in parallel on separate worktrees. None of
  them may modify `SessionState` fields or `core/commands.py`. They migrate
  readers off `region_masks` / `region_areas` while leaving the writes
  intact.
- **Wave 2** runs sequentially after wave 1 is merged. This is the anchor
  commit — it deletes `region_masks` / `region_areas` from state and prunes
  the masking helpers they supported. ruff + pytest are the forcing function
  for completeness.
- **Wave 3** is polish (benchmarks, doc updates). Can defer or fold into
  wave 2 if small.

## Files

| File | Session | Depends on |
|---|---|---|
| [wave-0-preflight.md](wave-0-preflight.md) | One-shot prep | — |
| [wave-1a-area-shift.md](wave-1a-area-shift.md) | Area → shoelace | Wave 0 |
| [wave-1b-canvas-overlay.md](wave-1b-canvas-overlay.md) | Canvas rebuilds from polygons | Wave 0 |
| [wave-1c-brush-commit.md](wave-1c-brush-commit.md) | Brush commit via transient raster | Wave 0 |
| [wave-2-anchor.md](wave-2-anchor.md) | Commands + state + masking prune | Wave 1 (all three) |
| [wave-3-polish.md](wave-3-polish.md) | Benchmarks + docs | Wave 2 |

## Ground rules every agent must follow

1. **Read the doctrine first.** `knowledge/030-polygons-are-mask-truth.md` is
   the anchor. If the brief contradicts 030, the doctrine wins — report and
   stop.
2. **Stay in scope.** Each brief lists files you may touch and files you may
   not touch. Violating scope blocks parallel sessions.
3. **Green tree on merge.** `uv run pytest` passes, `uv run ruff check` and
   `uv run ruff format --check` clean. No `--no-verify` bypasses.
4. **Commit granularity.** One focused commit per brief unless the brief
   says otherwise. Follow the repo's existing commit-message style (see
   `git log --oneline -20`).
5. **Report back.** Every brief ends with a Report section — one short
   paragraph summarizing what landed, what surprised you, what numbers
   changed.

## Non-removal invariant (waves 0–1 only)

During waves 0 and 1, `state.region_masks` and `state.region_areas` **must
continue to exist and be written**. Commands still maintain them. Other
in-flight sessions depend on them compiling. Only wave 2 removes them.

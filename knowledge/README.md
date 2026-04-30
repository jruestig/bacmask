# BacMask Knowledge Base

Zettelkasten-style notes for ideas, decisions, and design rationale. Preserves conversation context between sessions.

> **Session handoff:** [`_status.md`](_status.md) — in flight, next up, recently landed. Update at end of each session. Not a zettel — a rolling snapshot.

## Conventions

- **One idea per note.** Split if a note sprouts a second concept.
- **ID + slug filename:** `NNN-kebab-case-slug.md` (zero-padded 3 digits; branching IDs `001a`, `001a1` allowed for child thoughts).
- **Frontmatter** on every note:
  ```yaml
  ---
  id: 001
  title: Separation of Concerns
  tags: [architecture, core, ui]
  created: 2026-04-17
  status: accepted   # draft | proposed | accepted | superseded
  related: [002, 008]
  ---
  ```
- **Linking:** use relative markdown links `[Separation of Concerns](001-separation-of-concerns.md)`. Cross-reference liberally — links are the value.
- **Status lifecycle:** `draft` → `proposed` → `accepted` → `superseded` (link to the superseding note).
- **Atomic & self-contained:** a note should stand alone but link out for depth.
- **No status duplication:** obsolete notes get `status: superseded` and a forward link — do not delete.

## Index

### Meta
- [000 — Project Overview](000-project-overview.md)

### Architecture decisions (2026-04-17)
- [001 — Separation of Concerns](001-separation-of-concerns.md)
- [002 — State Management](002-state-management.md)
- [003 — Undo/Redo via Command Pattern](003-undo-redo-commands.md)
- [004 — Performance on Large Images](004-performance-large-images.md)
- [005 — Testing Strategy](005-testing-strategy.md)
- [006 — Configuration Management](006-configuration-management.md)
- [007 — Logging](007-logging.md)
- [008 — Directory Layout](008-directory-layout.md)
- [009 — Deviations from CLAUDE.md Sketch](009-deviations-from-claudemd.md)

### Technology & format choices (2026-04-17)
- [010 — Kivy over BeeWare](010-kivy-over-beeware.md)
- [011 — CSV for Area Output](011-csv-for-area-output.md)
- [013 — Minimal Toolset (MVP scope lock)](013-minimal-toolset.md)

### Product behavior & scope (2026-04-17)
- [014 — Lasso Tool (region creation)](014-lasso-tool.md)
- [015 — .bacmask Bundle Format](015-bacmask-bundle.md)
- [016 — Input Abstraction Layer](016-input-abstraction.md)
- [017 — Calibration Input Model](017-calibration-input.md)
- [019 — Development Tooling](019-dev-tooling.md)
- [020 — Platform Scope (Desktop-First MVP)](020-platform-scope.md)
- [022 — Region Split Helper (proposed, post-MVP)](022-region-split-helper.md)

### Product behavior & scope (2026-04-19)
- [024 — Mask Export (deferred, Python-only)](024-mask-export-deferred.md)
- [025 — Overlapping Regions Allowed](025-overlapping-regions.md)
- [026 — Brush Edit Model (Shift add / Ctrl subtract)](026-brush-edit-model.md)
- [027 — Toolbar Hotkey Labels](027-toolbar-hotkey-labels.md)
- [028 — File Picker Double-Click to Open](028-file-picker-double-click.md)

### Architecture doctrine (2026-04-19)
- [030 — Polygons Are the Only Mask Truth](030-polygons-are-mask-truth.md) — anchor: no per-region masks, area via shoelace, rendering and hit-testing are polygon projections. Supersedes 029.

### Navigation (2026-04-19)
- [031 — Minimap Navigator + Keyboard Pan](031-minimap-navigator.md)

### File I/O UX (2026-04-30)
- [032 — Save As / Export As Dialog (User-Chosen Path)](032-save-as-dialog.md) — Save/Export prompt for path; New Folder button; modal popups suppress global shortcuts; output dirs no longer auto-created.

### Superseded (archived in [`superseded/`](superseded/))
Retired decisions kept for reasoning trails and decision-record context. Do **not** implement against these — each carries a banner pointing to its replacement.

- [012 — 16-bit PNG Label Maps](superseded/012-png-label-maps.md) — superseded by 015 + 024 + 025. Masks are no longer persisted; polygons are canonical.
- [018 — Load Mask Dimension Mismatch](superseded/018-load-mask-dim-mismatch.md) — superseded by 015 + 025. No in-bundle mask to dimension-check.
- [021 — Edit Collision Policy (Clip)](superseded/021-vertex-edit-collision.md) — superseded by 025. Overlap is allowed; no clip rule.
- [023 — Edit Mode & Region Boolean Edits](superseded/023-edit-mode-region-boolean-edits.md) — superseded by 026. Brush replaces the lasso-against-region stroke.
- [029 — Incremental Overlay Compositor + Per-Region Area Cache](superseded/029-incremental-overlay-and-area-cache.md) — superseded by 030. The compositor+cache machinery existed to keep per-region masks in sync; with polygons canonical there are no masks to cache.

## Tags
- `architecture` — structural decisions
- `core` — applies to `bacmask/core/` package
- `services` — applies to `bacmask/services/` package
- `ui` — applies to `bacmask/ui/` package
- `testing` — test strategy & fixtures
- `perf` — performance / scalability
- `config` — configuration & defaults
- `ops` — logging, build, deployment

## How to add a note

1. Pick next ID (or branch under a parent, e.g. `003a` for a sub-thought of 003).
2. Create `NNN-slug.md` with frontmatter.
3. Add link under appropriate Index section above.
4. Add backlinks: append this note to each related note's `related:` list and/or "Related" section.

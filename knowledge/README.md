# BacMask Knowledge Base

Zettelkasten-style notes for ideas, decisions, and design rationale. Conversation retainment between sessions.

## Conventions

- **One idea per note.** If a note sprouts a second concept, split it.
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
- **Atomic & self-contained:** a note should make sense without reading the whole base, but should link out for depth.
- **No status duplication:** if a note becomes obsolete, mark `status: superseded` and link forward — do not delete.

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
- [012 — 16-bit PNG Label Maps](012-png-label-maps.md)
- [013 — Minimal Toolset (MVP scope lock)](013-minimal-toolset.md)

### Product behavior & scope (2026-04-17)
- [014 — Lasso Tool & Boundary Editing](014-lasso-tool.md)
- [015 — .bacmask Bundle Format](015-bacmask-bundle.md)
- [016 — Input Abstraction Layer](016-input-abstraction.md)
- [017 — Calibration Input Model](017-calibration-input.md)
- [018 — Load Mask Dimension Mismatch](018-load-mask-dim-mismatch.md)
- [019 — Development Tooling](019-dev-tooling.md)
- [020 — Platform Scope (Desktop-First MVP)](020-platform-scope.md)
- [021 — Vertex-Edit Collision Policy (Clip)](021-vertex-edit-collision.md)
- [022 — Region Split Helper (proposed, post-MVP)](022-region-split-helper.md)

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
4. Add backlinks: in each related note, append this note to its `related:` list and/or "Related" section.

---
id: 011
title: CSV for Area Output
tags: [architecture, core]
created: 2026-04-17
status: accepted
related: [000, 005, 012, 014, 015, 017]
---

# CSV for Area Output

Per-region areas exported as CSV, one file per image. Sibling to the `.bacmask` bundle ([015](015-bacmask-bundle.md)) — serves as human-readable double-bookkeeping.

## Schema (locked)
Column order is load-bearing. Header row always written.

```
filename, region_id, region_name, area_px, area_mm2, scale_factor
```

| Column | Type | Notes |
| --- | --- | --- |
| `filename` | str | Full source filename with extension (e.g. `20251112093808947.tif`). Not a path. |
| `region_id` | int | Auto-assigned, monotonic, never reused. See [014](014-lasso-tool.md). |
| `region_name` | str | Auto-generated (`region_01`, `region_02`, …). Future: user-editable. |
| `area_px` | int | Always populated. Canonical measurement. |
| `area_mm2` | float or "" | Empty string when uncalibrated. |
| `scale_factor` | float or "" | mm per pixel. Empty when uncalibrated. |

## Rules
- One row per region.
- One CSV per image, named `<image_stem>_areas.csv` (output dir configurable — see [006](006-configuration-management.md)).
- Re-save **overwrites** (does not append).
- Plain text — directly readable in any editor. No binary, no base64, no embedded JSON.
- Dialect: comma separator, `\n` line terminator, minimal quoting (only when a value contains `,` or `"`).

## Uncalibrated rows
`area_mm2` and `scale_factor` are empty strings — not `NaN`, not `0`. Empty preserves the "unknown" semantic without a magic number. See [017 — Calibration Input](017-calibration-input.md).

## Rationale
- **Universal consumption.** pandas, Excel, R, Julia — zero parser overhead.
- **Human-readable.** Open in any text editor. Sanity-check values instantly.
- **Diff-friendly.** Plays nice with version control if users commit outputs.
- **No ceremony.** Per-region tabular area data has no nesting. JSON or SQLite would add overhead for no gain.

## Why CSV lives outside the bundle
- Bundle ([015](015-bacmask-bundle.md)) is the source of truth; CSV is derived and regenerable.
- Keeping the CSV as a standalone sibling file preserves its direct-read value — no unzipping needed.

## When we'd revisit
Multi-image aggregation becoming a first-class feature → long-form CSV across all images (grouped by `filename`) or parquet. Out of MVP.

## Related
- [015 — .bacmask Bundle](015-bacmask-bundle.md).
- [014 — Lasso Tool](014-lasso-tool.md) — ID assignment rules.
- [017 — Calibration Input](017-calibration-input.md) — uncalibrated semantics.
- [005 — Testing Strategy](005-testing-strategy.md) — CSV contract tests.

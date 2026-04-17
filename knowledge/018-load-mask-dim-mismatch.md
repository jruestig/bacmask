---
id: 018
title: Load Mask Dimension Mismatch
tags: [core]
created: 2026-04-17
status: accepted
related: [012]
---

# Load Mask Dimension Mismatch

## Decision
When a user loads a mask PNG (or `.bacmask` bundle whose mask differs from the current image) with `(H, W)` not matching the currently loaded image:

1. Show a modal dialog with both dimensions, e.g.:
   > "Mask size **3000 × 4000** does not match image size **2048 × 2048**. Load anyway?"
2. **Default button: Reject.**
3. Secondary button: **Resize to fit (nearest-neighbor, lossy)** — with a warning label attached.

## Why prompt rather than silent reject
The user explicitly asked for a prompt-with-rejection-default — leaves an out for the rare case where they know the resize is intentional (e.g. downsampled workflow) without creating a trap.

## Why reject by default
- Labels are discrete integers. Any non-nearest-neighbor resize silently corrupts them.
- Even nearest-neighbor can split thin regions or merge adjacent ones.
- Silently proceeding would corrupt training data without warning.

## Why offer the lossy path at all
Occasional power-user need. Gating it behind a non-default button with a visible warning is the right trade-off.

## Implementation notes
- Resize uses `cv2.resize(..., interpolation=cv2.INTER_NEAREST)`.
- After resize, log at `WARNING` level with old/new dims ([007](007-logging.md)).
- Sets the `dirty` flag — user must explicitly save if they want the resized result persisted.
- The bundle's `meta.json` vertex lists are also resized proportionally and a warning is added to the bundle's next-save audit trail (post-MVP).

## Related
- [012 — 16-bit PNG Label Maps](012-png-label-maps.md).

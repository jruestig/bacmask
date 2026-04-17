---
id: 019
title: Development Tooling
tags: [ops]
created: 2026-04-17
status: accepted
related: [005, 006, 008]
---

# Development Tooling

## Python
- **Python 3.12** is the managed target. No support for older minors in MVP.
- `pyproject.toml` sets `requires-python = ">=3.12,<3.13"`.

## Environment manager: uv
- [uv](https://docs.astral.sh/uv/) handles venv creation, dep resolution, lockfile, and script running.
- `uv sync` gives every contributor the exact same environment.
- `uv.lock` is committed. Exact versions pinned.
- No `pip`, no `poetry`, no `requirements.txt`.

### Why uv
- Single tool; replaces pip + pip-tools + virtualenv + sometimes poetry.
- Fast (Rust-backed; 10–100× pip resolution speed).
- Lockfile produces reproducible installs across Linux/Windows/macOS.

## Formatter + linter: Ruff
- Ruff handles both formatting and linting. No black, isort, or flake8.
- Configured in `pyproject.toml` under `[tool.ruff]`.
- Default rule groups: `E`, `F`, `I`, `B`, `UP`. Expand as real friction appears — don't pre-adopt every rule.
- Format on save is a contributor choice; CI enforces `ruff check` and `ruff format --check`.

## Type checking
Not adopted in MVP. Revisit if type bugs become a pattern. When adopted: mypy with `--strict` scoped to `core/` first.

## Testing
- pytest. Fixtures in `tests/fixtures/` ([005](005-testing-strategy.md)).
- `pytest-cov` for coverage reporting.

## Real-world test images
Live at `images/` (repo root):
- `20251112093808947.tif` (~22 MB)
- `20251201151902553.tif` (~18 MB)

These are **manual smoke tests and profiling inputs**, not CI fixtures — too large and slow for the unit test loop. Unit tests use small synthetic fixtures.

## CI
Undecided for MVP. When adopted: GitHub Actions, matrix on Linux + Windows (macOS optional), running:
1. `uv sync --frozen`
2. `ruff check && ruff format --check`
3. `pytest -q`

Android/Buildozer builds excluded from CI — run locally.

## Dev dependencies (declared in `pyproject.toml` dev group)
- pytest
- pytest-cov
- ruff
- (mypy — deferred)

## Related
- [005 — Testing Strategy](005-testing-strategy.md).
- [006 — Configuration Management](006-configuration-management.md) — runtime config vs. dev tooling.
- [008 — Directory Layout](008-directory-layout.md) — where `pyproject.toml` + `uv.lock` live.

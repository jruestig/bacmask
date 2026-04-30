#!/usr/bin/env python3
"""Bump BacMask version across pyproject.toml, version_info.txt, installer.iss.

Usage:
    uv run scripts/bump_version.py 0.0.5
    uv run scripts/bump_version.py 0.0.5 --tag        # also git tag + push
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYPROJECT = REPO / "pyproject.toml"
UV_LOCK = REPO / "uv.lock"
VERSION_INFO = REPO / "packaging" / "version_info.txt"
INSTALLER = REPO / "packaging" / "installer.iss"

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def parse(v: str) -> tuple[int, int, int]:
    m = SEMVER.match(v)
    if not m:
        sys.exit(f"version must be MAJOR.MINOR.PATCH, got: {v}")
    return int(m[1]), int(m[2]), int(m[3])


def sub(path: Path, pattern: str, replacement: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    new, n = re.subn(pattern, replacement, text, count=count, flags=re.MULTILINE)
    if n != count:
        sys.exit(f"{path}: expected {count} replacement(s), made {n} for /{pattern}/")
    path.write_text(new, encoding="utf-8")


def bump(version: str) -> None:
    major, minor, patch = parse(version)
    sub(PYPROJECT, r'^version = "[^"]+"', f'version = "{version}"')
    sub(
        VERSION_INFO,
        r"filevers=\(\d+, \d+, \d+, \d+\)",
        f"filevers=({major}, {minor}, {patch}, 0)",
    )
    sub(
        VERSION_INFO,
        r"prodvers=\(\d+, \d+, \d+, \d+\)",
        f"prodvers=({major}, {minor}, {patch}, 0)",
    )
    sub(
        VERSION_INFO,
        r"u'FileVersion', u'[^']+'",
        f"u'FileVersion', u'{version}'",
    )
    sub(
        VERSION_INFO,
        r"u'ProductVersion', u'[^']+'",
        f"u'ProductVersion', u'{version}'",
    )
    sub(
        INSTALLER,
        r'#define MyAppVersion\s+"[^"]+"',
        f'#define MyAppVersion    "{version}"',
    )
    print(f"bumped to {version}:")
    print(f"  {PYPROJECT.relative_to(REPO)}")
    print(f"  {VERSION_INFO.relative_to(REPO)}")
    print(f"  {INSTALLER.relative_to(REPO)}")


def relock() -> None:
    subprocess.run(["uv", "lock"], check=True, cwd=REPO)
    print(f"  {UV_LOCK.relative_to(REPO)}")


def git(*args: str) -> None:
    subprocess.run(["git", *args], check=True, cwd=REPO)


def commit_and_tag(version: str) -> None:
    git("add", str(PYPROJECT), str(UV_LOCK), str(VERSION_INFO), str(INSTALLER))
    git("commit", "-m", f"chore: bump version to {version}")
    git("tag", f"v{version}")
    git("push")
    git("push", "origin", f"v{version}")
    print(f"committed, tagged v{version}, pushed")


def main() -> None:
    ap = argparse.ArgumentParser(description="bump BacMask version in lockstep")
    ap.add_argument("version", help="new version, e.g. 0.0.5")
    ap.add_argument(
        "--tag",
        action="store_true",
        help="git commit + tag v<version> + push (otherwise just edit files)",
    )
    args = ap.parse_args()
    bump(args.version)
    relock()
    if args.tag:
        commit_and_tag(args.version)


if __name__ == "__main__":
    main()

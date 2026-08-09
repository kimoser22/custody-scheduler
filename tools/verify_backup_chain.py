#!/usr/bin/env python3
"""Verify a folder of custody-archive files against their hash chain.

Usage:
    python tools/verify_backup_chain.py <folder-of-saved-attachments>

Stdlib plus core/backup.py only — runs on any laptop against the .json
attachments saved from the weekly backup emails. Two independent checks per
file: the raw bytes' SHA-256 (byte integrity — never computed over
re-canonicalized content, which would launder byte-level edits away), and that
the bytes are canonical archive format v1. Then the prev_sha256 links are
followed to build the chain.

Exit code 0 only when the chain verifies and every file is accounted for.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from a repo checkout without installing anything.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.backup import sha256_hex, verify_chain  # noqa: E402


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2

    folder = Path(argv[1])
    paths = sorted(folder.glob("*.json"))
    if not paths:
        print(f"no .json archives found in {folder}")
        return 2

    files: list[bytes] = []
    for path in paths:
        raw = path.read_bytes()
        files.append(raw)
        print(f"  {path.name}: sha256 {sha256_hex(raw)}")

    result = verify_chain(files)

    print()
    if result.chain:
        print("chain:")
        for member in result.chain:
            prev = member.prev_sha256[:12] + "…" if member.prev_sha256 else "(genesis)"
            print(f"  {member.backup_date}  {member.sha256[:12]}…  prev {prev}")
    for digest in result.failed_branches:
        print(f"failed branch (corroborated by later history): {digest[:12]}…")
    for digest in result.unexplained_branches:
        print(f"UNEXPLAINED BRANCH: {digest[:12]}… — investigate before trusting")
    for problem in result.problems:
        print(f"PROBLEM: {problem}")

    if result.ok:
        print(f"\nOK: chain of {len(result.chain)} archive(s) verifies.")
        return 0
    print("\nFAILED: the archive set does not verify. See problems above.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

"""Canonical bytes, hashing, and chain verification for the evidence archive.

The archive format outlives the app: a verifier reimplemented independently
years from now must produce the same bytes and the same digests from the same
data. That is why canonicalization is specified (sort_keys, tight separators,
ensure_ascii=False, allow_nan=False, UTF-8) and pinned by a golden fixture,
rather than being whatever json.dumps happens to do this year.
"""

import json
from pathlib import Path

import pytest

from core.backup import (
    ARCHIVE_FORMAT_VERSION,
    build_archive_document,
    canonical_bytes,
    sha256_hex,
    verify_chain,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _archive(backup_date: str, prev: str | None, data: dict) -> bytes:
    """Canonical bytes of a minimal but format-valid archive."""
    return canonical_bytes(
        build_archive_document(
            backup_date=backup_date,
            created_at_iso=f"{backup_date}T03:17:12Z",
            prev_sha256=prev,
            recipient_parent_ids=[101, 102],
            data=data,
        )
    )


# --- canonicalization ----------------------------------------------------------


def test_canonical_bytes_are_stable_across_key_order() -> None:
    a = canonical_bytes({"b": 1, "a": {"y": 2, "x": 3}})
    b = canonical_bytes({"a": {"x": 3, "y": 2}, "b": 1})
    assert a == b


def test_canonical_bytes_are_compact_utf8() -> None:
    encoded = canonical_bytes({"name": "Mosér", "n": 1})
    assert b" " not in encoded  # tight separators, no pretty-printing
    assert "Mosér".encode("utf-8") in encoded  # ensure_ascii=False, real UTF-8


def test_nan_is_rejected_not_serialized() -> None:
    """allow_nan=False: NaN has no JSON meaning and would break independent
    verifiers; better to crash the build than emit unverifiable bytes."""
    with pytest.raises(ValueError):
        canonical_bytes({"x": float("nan")})


def test_golden_fixture_hash_matches() -> None:
    """The 2038 test: these two committed files pin the format. If this fails,
    canonicalization changed and old archives would stop verifying."""
    raw = (FIXTURES / "canonical-v1.json").read_bytes()
    expected = (FIXTURES / "canonical-v1.sha256").read_text().strip()

    assert sha256_hex(raw) == expected
    # And the fixture itself is canonical: re-canonicalizing is a no-op.
    assert canonical_bytes(json.loads(raw.decode("utf-8"))) == raw


# --- chain verification --------------------------------------------------------


def _chain_of_three() -> list[bytes]:
    a = _archive("2026-08-02", None, {"note": "week 1"})
    b = _archive("2026-08-09", sha256_hex(a), {"note": "week 2"})
    c = _archive("2026-08-16", sha256_hex(b), {"note": "week 3"})
    return [a, b, c]


def test_valid_three_link_chain_verifies() -> None:
    result = verify_chain(_chain_of_three())
    assert result.ok
    assert len(result.chain) == 3
    assert result.unexplained_branches == []


def test_single_file_chain_verifies() -> None:
    result = verify_chain([_archive("2026-08-02", None, {"note": "first"})])
    assert result.ok
    assert len(result.chain) == 1


def test_tampered_middle_file_fails() -> None:
    """The point of the feature: editing an already-archived file must be
    detectable. Flip one byte of archive 2 of 3 — its hash no longer matches
    archive 3's prev_sha256."""
    a, b, c = _chain_of_three()
    tampered = b.replace(b"week 2", b"week 2!")

    result = verify_chain([a, tampered, c])
    assert not result.ok


def test_broken_prev_link_fails() -> None:
    a = _archive("2026-08-02", None, {"note": "week 1"})
    b = _archive("2026-08-09", "0" * 64, {"note": "week 2"})  # wrong prev

    result = verify_chain([a, b])
    assert not result.ok


def test_prev_sha256_is_inside_the_hashed_bytes() -> None:
    """Mutating the manifest's prev pointer must change the file's own hash —
    otherwise the chain links wouldn't be covered by the digests."""
    original = _archive("2026-08-09", "a" * 64, {"note": "x"})
    relinked = _archive("2026-08-09", "b" * 64, {"note": "x"})
    assert sha256_hex(original) != sha256_hex(relinked)


def test_corroborated_dead_branch_is_classified_failed() -> None:
    """Two files share a predecessor. The chain member's embedded history
    records the other as a failed attempt -> classified, not alarming."""
    a = _archive("2026-08-02", None, {"note": "week 1"})
    failed = _archive("2026-08-09", sha256_hex(a), {"note": "failed attempt"})
    succeeded = _archive(
        "2026-08-10",
        sha256_hex(a),
        {
            "note": "the real week 2",
            "backup_records": [
                {"backup_date": "2026-08-09", "sha256": sha256_hex(failed),
                 "status": "failed"},
            ],
        },
    )

    result = verify_chain([a, failed, succeeded])
    assert result.ok
    assert [m.sha256 for m in result.chain] == [sha256_hex(a), sha256_hex(succeeded)]
    assert result.failed_branches == [sha256_hex(failed)]
    assert result.unexplained_branches == []


def test_uncorroborated_branch_is_reported_not_guessed() -> None:
    """Without later history naming the branch, the verifier must say
    'unexplained', never confidently call it an orphan — a fork it cannot
    explain is exactly what it exists to surface."""
    a = _archive("2026-08-02", None, {"note": "week 1"})
    b1 = _archive("2026-08-09", sha256_hex(a), {"note": "branch one"})
    b2 = _archive("2026-08-10", sha256_hex(a), {"note": "branch two"})

    result = verify_chain([a, b1, b2])
    assert not result.ok
    assert set(result.unexplained_branches) == {sha256_hex(b1), sha256_hex(b2)} - {
        m.sha256 for m in result.chain
    }


def test_format_version_present() -> None:
    doc = json.loads(_archive("2026-08-02", None, {}).decode("utf-8"))
    assert doc["archive_manifest"]["format"] == "custody-archive"
    assert doc["archive_manifest"]["archive_format_version"] == ARCHIVE_FORMAT_VERSION


def test_every_file_must_be_accounted_for() -> None:
    """A forged continuation of a corroborated-failed branch must not slide
    through unaccounted: OK means every file is chain, failed, or flagged."""
    a = _archive("2026-08-02", None, {"note": "week 1"})
    failed = _archive("2026-08-09", sha256_hex(a), {"note": "failed attempt"})
    succeeded = _archive(
        "2026-08-10",
        sha256_hex(a),
        {
            "note": "real week 2",
            "backup_records": [
                {"backup_date": "2026-08-09", "sha256": sha256_hex(failed),
                 "status": "failed"},
            ],
        },
    )
    forged = _archive("2026-08-16", sha256_hex(failed), {"note": "forged"})

    result = verify_chain([a, failed, succeeded, forged])

    assert not result.ok
    assert sha256_hex(forged) in result.unexplained_branches

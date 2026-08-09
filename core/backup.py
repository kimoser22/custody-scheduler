"""Evidence archive: canonical bytes, hash chain, and chain verification.

Invariants (the endpoint in api/backup_router.py enforces the first three;
verify_chain checks what they produce):

1. One backup_date identifies exactly one immutable archive byte sequence and
   SHA-256 digest, regardless of how many delivery attempts occur.
2. A backup record with status "submitted" means those exact bytes were
   successfully handed to the SMTP server for every required parent IDENTITY.
   Only submitted records participate in the hash chain.
3. At most one process owns delivery of a backup record at any instant;
   ownership may be recovered after an expired lease.

What the chain provides: tamper-evident, independently replicated archival
snapshots. Modification, deletion, insertion, or reordering of previously
archived content is detectable given the archived sequence. It does not prove
the truth of what was entered, and SHA-256 proves no absolute time — the
received-timestamps on the copies in two independently controlled mailboxes
are corroborating chronology, not a cryptographic timestamp.

ARCHIVE_FORMAT_VERSION is deliberately distinct from the database export's
EXPORT_SCHEMA_VERSION: the app and its schema may be rewritten years from now,
but archives written today must still verify. Canonicalization is therefore a
specification, pinned by tests/fixtures/canonical-v1.json — not whatever
json.dumps happens to do this year.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

ARCHIVE_FORMAT = "custody-archive"
ARCHIVE_FORMAT_VERSION = 1


def canonical_bytes(payload: dict[str, Any]) -> bytes:
    """The exact bytes that get hashed, attached, and stored.

    sort_keys + tight separators: independent of dict construction order.
    ensure_ascii=False: real UTF-8, not escape sequences.
    allow_nan=False: NaN has no JSON meaning; crash rather than emit bytes an
    independent verifier cannot reproduce.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_archive_document(
    *,
    backup_date: str,
    created_at_iso: str,
    prev_sha256: str | None,
    recipient_parent_ids: list[int],
    data: dict[str, Any],
) -> dict[str, Any]:
    """Self-describing archive: the manifest travels inside the hashed bytes,
    so each file states its own chain position (prev_sha256) and the parent
    identities it was required to reach. Its own hash cannot be inside itself;
    that lives in the email body, the backup_records row, and the next
    archive's prev_sha256.

    recipient_parent_ids freezes WHO must receive the archive. Delivery
    addresses are deliberately absent: they are operational state, read fresh
    at each attempt and recorded per attempt in backup_deliveries, so a typo'd
    email is correctable without abandoning an immutable archive.
    """
    return {
        "archive_manifest": {
            "format": ARCHIVE_FORMAT,
            "archive_format_version": ARCHIVE_FORMAT_VERSION,
            "backup_date": backup_date,
            "created_at": created_at_iso,
            "prev_sha256": prev_sha256,
            "recipient_parent_ids": sorted(recipient_parent_ids),
        },
        "data": data,
    }


@dataclass(frozen=True)
class ChainMember:
    sha256: str
    backup_date: str
    prev_sha256: str | None


@dataclass
class ChainResult:
    ok: bool
    chain: list[ChainMember] = field(default_factory=list)
    failed_branches: list[str] = field(default_factory=list)
    unexplained_branches: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)


def _parse_member(raw: bytes) -> tuple[ChainMember, dict[str, Any]] | str:
    """Returns the member and parsed doc, or an error string.

    Two independent checks, in order:
    1. (Caller's job) the raw bytes' sha256 is the file's identity — computed
       here over raw bytes, never over re-canonicalized content, which would
       launder away byte-level modifications.
    2. The file conforms to the format: parsing then re-canonicalizing must
       reproduce the raw bytes exactly.
    """
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "not valid UTF-8 JSON"
    if canonical_bytes(doc) != raw:
        return "bytes are not in canonical form (format check failed)"
    manifest = doc.get("archive_manifest")
    if not isinstance(manifest, dict) or manifest.get("format") != ARCHIVE_FORMAT:
        return "missing or foreign archive_manifest"
    return (
        ChainMember(
            sha256=sha256_hex(raw),
            backup_date=str(manifest.get("backup_date")),
            prev_sha256=manifest.get("prev_sha256"),
        ),
        doc,
    )


def verify_chain(files: list[bytes]) -> ChainResult:
    """Build and verify the hash chain across a set of raw archive files.

    Chain construction follows prev_sha256 links from the unique genesis
    (prev=None) forward, preferring at each step the successor that the later
    archives' embedded backup_records corroborate as submitted.

    Branch semantics: a partially distributed failed archive cannot itself say
    "I failed" — that outcome postdates its immutable bytes. A dead branch is
    classified `failed` only when a LATER archive's embedded backup_records
    records that hash with a non-submitted status; otherwise it is reported as
    an unexplained branch and verification does not pass. The verifier never
    guesses.
    """
    result = ChainResult(ok=True)
    members: dict[str, ChainMember] = {}
    docs: dict[str, dict[str, Any]] = {}

    for index, raw in enumerate(files):
        parsed = _parse_member(raw)
        if isinstance(parsed, str):
            result.ok = False
            result.problems.append(f"file {index}: {parsed}")
            continue
        member, doc = parsed
        members[member.sha256] = member
        docs[member.sha256] = doc

    if not members:
        result.ok = False
        result.problems.append("no valid archive files")
        return result

    # Statuses corroborated by embedded history in ANY file.
    corroborated: dict[str, str] = {}
    for doc in docs.values():
        for record in doc.get("data", {}).get("backup_records", []) or []:
            digest = record.get("sha256")
            status = record.get("status")
            if isinstance(digest, str) and isinstance(status, str):
                corroborated[digest] = status

    by_prev: dict[str | None, list[ChainMember]] = {}
    for member in members.values():
        by_prev.setdefault(member.prev_sha256, []).append(member)

    genesis = by_prev.get(None, [])
    if len(genesis) != 1:
        result.ok = False
        result.problems.append(
            f"expected exactly one genesis archive (prev=null), found {len(genesis)}"
        )
        return result

    current = genesis[0]
    result.chain.append(current)
    on_chain = {current.sha256}

    while True:
        successors = by_prev.get(current.sha256, [])
        if not successors:
            break
        if len(successors) == 1:
            current = successors[0]
        else:
            # A fork. Only proceed if embedded history explains all but one.
            alive = [
                s for s in successors
                if corroborated.get(s.sha256) in (None, "submitted")
            ]
            dead = [s for s in successors if s not in alive]
            for member in dead:
                result.failed_branches.append(member.sha256)
            if len(alive) != 1:
                result.ok = False
                for member in alive:
                    result.unexplained_branches.append(member.sha256)
                result.problems.append(
                    f"unexplained fork after {current.sha256[:12]}…"
                )
                break
            current = alive[0]
        result.chain.append(current)
        on_chain.add(current.sha256)

    # Every file must end up accounted for: on the chain, corroborated as a
    # failed attempt, or explicitly flagged. There is no silent bucket — a
    # file the verifier cannot place (a continuation of a failed branch, a
    # link to an unknown predecessor, a detached subgraph) is exactly what it
    # exists to surface, so anything left over fails verification.
    for digest, member in members.items():
        if digest in on_chain or digest in result.failed_branches:
            continue
        if digest in result.unexplained_branches:
            continue
        if corroborated.get(digest) not in (None, "submitted"):
            result.failed_branches.append(digest)
            continue
        result.ok = False
        result.unexplained_branches.append(digest)
        if member.prev_sha256 in members:
            result.problems.append(
                f"{digest[:12]}… is not on the chain and no later history "
                "explains it"
            )
        else:
            result.problems.append(
                f"{digest[:12]}… links to an unknown predecessor "
                f"{str(member.prev_sha256)[:12]}…"
            )

    return result

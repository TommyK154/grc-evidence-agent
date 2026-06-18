"""Human approval queue for proposed evidence-to-control mappings.

Mappings proposed by :mod:`agent.mapper` never auto-accept. Each lands in the
queue as ``pending`` and is written to two artifacts:

    - ``review_queue.json``: machine-readable queue state.
    - ``REVIEW.md``: human-readable summary for the reviewer.

A mapping only becomes ``approved`` when a human explicitly approves it via
:func:`approve` (or the ``approve`` CLI subcommand). This module is the
enforcement point for the "nothing auto-accepts" design principle: ``approved``
status is reachable through :func:`approve` and nowhere else.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from typing import Any

from agent.mapper import Mapping

QUEUE_PATH = "review_queue.json"
REVIEW_MD_PATH = "REVIEW.md"
INVENTORY_PATH = "evidence_inventory.json"

QUEUE_VERSION = "v1"

# Max length of the raw-evidence summary shown per evidence id in REVIEW.md.
_SUMMARY_MAX_LEN = 160


def _now_iso() -> str:
    """Return the current time as an ISO-8601 UTC timestamp.

    Matches the convention used by ``Evidence.collected_at`` so timestamps are
    consistent across the pipeline.

    Returns:
        The current UTC time, e.g. ``"2026-06-15T12:34:56.789012+00:00"``.
    """
    return datetime.now(timezone.utc).isoformat()


def _proposal_key(item: Mapping | dict[str, Any]) -> tuple[tuple[str, ...], str, str]:
    """Return the proposal-identity fields of a mapping or queue entry.

    Two proposals are considered identical when they cite the same evidence
    (order-insensitive) with the same confidence and rationale. This is the key
    used to decide whether a prior human approval still applies after a fresh
    mapper run.

    Args:
        item: A :class:`agent.mapper.Mapping` or a queue-entry dict.

    Returns:
        A ``(sorted_evidence_ids, confidence, rationale)`` tuple.
    """
    if isinstance(item, Mapping):
        evidence_ids = item.evidence_ids
        confidence = item.confidence
        rationale = item.rationale
    else:
        evidence_ids = item.get("evidence_ids", [])
        confidence = item.get("confidence", "")
        rationale = item.get("rationale", "")
    return (tuple(sorted(evidence_ids)), confidence, rationale)


def _mapping_to_entry(mapping: Mapping) -> dict[str, Any]:
    """Build a fresh ``pending`` queue entry from a proposed mapping.

    Args:
        mapping: The proposed mapping to record.

    Returns:
        A queue-entry dict with status ``pending`` and no reviewer/decision yet.
    """
    return {
        "control_id": mapping.control_id,
        "evidence_ids": list(mapping.evidence_ids),
        "confidence": mapping.confidence,
        "rationale": mapping.rationale,
        "status": "pending",
        "reviewer": None,
        "decided_at": None,
    }


def _read_queue_file() -> dict[str, Any]:
    """Read the full queue structure from ``review_queue.json``.

    Returns:
        The parsed queue object (``version``, ``generated_at``, ``entries``), or
        an empty-entries skeleton if the file does not exist.
    """
    try:
        with open(QUEUE_PATH, encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        return {"version": QUEUE_VERSION, "generated_at": None, "entries": []}


def _write_queue_file(entries: list[dict[str, Any]]) -> None:
    """Persist queue entries to both ``review_queue.json`` and ``REVIEW.md``.

    Args:
        entries: The queue entries to write, in control order.
    """
    queue_obj = {
        "version": QUEUE_VERSION,
        "generated_at": _now_iso(),
        "entries": entries,
    }
    with open(QUEUE_PATH, "w", encoding="utf-8") as handle:
        json.dump(queue_obj, handle, indent=2)
        handle.write("\n")
    with open(REVIEW_MD_PATH, "w", encoding="utf-8") as handle:
        handle.write(_render_review_md(queue_obj))


def _load_inventory() -> dict[str, dict[str, Any]]:
    """Load the evidence inventory as an id-keyed lookup, if it exists.

    ``evidence_inventory.json`` is written by the pipeline orchestrator
    (``run.py``) and maps each evidence id back to its source, type, raw
    payload, and collection time. It lets ``REVIEW.md`` resolve the opaque
    evidence ids in each proposal to something a human can audit. The file is
    optional: if it is absent or unreadable, rendering degrades to bare ids.

    Returns:
        A dict keyed by evidence id whose values are the full evidence records,
        or an empty dict when the inventory is unavailable.
    """
    try:
        with open(INVENTORY_PATH, encoding="utf-8") as handle:
            records = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(records, list):
        return {}
    return {
        record["id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("id"), str)
    }


def _summarize_evidence(evidence_id: str, inventory: dict[str, dict[str, Any]]) -> str:
    """Render one evidence id with its resolved source, type, time, and summary.

    Args:
        evidence_id: The evidence id cited by a proposal.
        inventory: The id-keyed lookup from :func:`_load_inventory`.

    Returns:
        A single Markdown line. When the id resolves against the inventory it
        reads ``id`: source / type · collected_at · <raw note>``; when it does
        not (no inventory, or an unknown id) it falls back to the bare id so the
        reviewer still sees exactly what the proposal cited.
    """
    record = inventory.get(evidence_id)
    if record is None:
        return f"`{evidence_id}`"

    raw = record.get("raw")
    note = raw.get("note") if isinstance(raw, dict) else None
    summary = " ".join(str(note).split()) if note else "(no summary in raw payload)"
    if len(summary) > _SUMMARY_MAX_LEN:
        summary = summary[: _SUMMARY_MAX_LEN - 1].rstrip() + "…"

    return (
        f"`{evidence_id}`: {record.get('source')} / {record.get('type')} "
        f"· collected {record.get('collected_at')} · {summary}"
    )


def _render_review_md(queue_obj: dict[str, Any]) -> str:
    """Render the human-readable ``REVIEW.md`` from a queue object.

    Each cited evidence id is resolved against ``evidence_inventory.json`` (when
    present) to its source, type, a short raw summary, and collection time, so a
    reviewer does not have to chase opaque ids. Rendering is display-only: it
    does not alter queue entries, approval state, or proposal identity.

    Args:
        queue_obj: The full queue object (``version``, ``generated_at``,
            ``entries``).

    Returns:
        The Markdown document as a string.
    """
    entries = queue_obj.get("entries", [])
    pending = sum(1 for e in entries if e.get("status") == "pending")
    approved = sum(1 for e in entries if e.get("status") == "approved")
    inventory = _load_inventory()

    lines = [
        "# Evidence-to-Control Review Queue",
        "",
        f"_Generated: {queue_obj.get('generated_at')}_",
        "",
        f"**{pending} pending**, **{approved} approved** "
        f"({len(entries)} total). Nothing is accepted until a human approves it.",
        "",
    ]

    for entry in entries:
        evidence_ids = entry.get("evidence_ids") or []
        lines.append(f"## {entry.get('control_id')}: {entry.get('status')}")
        lines.append("")
        lines.append(f"- **Confidence:** {entry.get('confidence')}")
        if evidence_ids:
            lines.append("- **Evidence:**")
            for eid in evidence_ids:
                lines.append(f"  - {_summarize_evidence(eid, inventory)}")
        else:
            lines.append("- **Evidence:** _none (no mapping proposed)_")
        lines.append(f"- **Rationale:** {entry.get('rationale')}")
        if entry.get("status") == "approved":
            lines.append(
                f"- **Approved by:** {entry.get('reviewer')} "
                f"at {entry.get('decided_at')}"
            )
        lines.append("")

    return "\n".join(lines)


def enqueue_pending(mappings: list[Mapping]) -> None:
    """Add proposed mappings to the queue as ``pending`` and rewrite artifacts.

    A fresh mapper run supersedes the prior proposals. For each incoming mapping
    a new ``pending`` entry is built, except where a prior entry for the same
    control was already ``approved`` *and* the re-proposed mapping is identical
    (same evidence ids, confidence, and rationale): in that case the existing
    approval (status, reviewer, decision time) is carried over. Any change to a
    proposal resets that control to ``pending``, a human approval never
    silently covers a different mapping.

    Args:
        mappings: Proposed mappings (see :class:`agent.mapper.Mapping`) to queue
            for human review.
    """
    prior = {entry["control_id"]: entry for entry in _read_queue_file().get("entries", [])}

    entries: list[dict[str, Any]] = []
    for mapping in mappings:
        entry = _mapping_to_entry(mapping)
        previous = prior.get(mapping.control_id)
        if (
            previous is not None
            and previous.get("status") == "approved"
            and _proposal_key(previous) == _proposal_key(mapping)
        ):
            entry["status"] = "approved"
            entry["reviewer"] = previous.get("reviewer")
            entry["decided_at"] = previous.get("decided_at")
        entries.append(entry)

    _write_queue_file(entries)


def load_queue() -> list[dict[str, Any]]:
    """Load the current review queue from ``review_queue.json``.

    Returns:
        The queue entries, each a dict including its ``status``. Returns an empty
        list if the queue file does not exist yet.
    """
    return _read_queue_file().get("entries", [])


def approve(control_id: str, reviewer: str) -> None:
    """Mark a pending mapping as approved by a human reviewer.

    Args:
        control_id: The control whose pending mapping is being approved.
        reviewer: Identifier of the human approving the mapping.

    Raises:
        ValueError: If no queue entry exists for ``control_id``.
    """
    queue_obj = _read_queue_file()
    entries = queue_obj.get("entries", [])
    for entry in entries:
        if entry.get("control_id") == control_id:
            entry["status"] = "approved"
            entry["reviewer"] = reviewer
            entry["decided_at"] = _now_iso()
            _write_queue_file(entries)
            return
    raise ValueError(f"no queue entry for control {control_id!r}")


def _cmd_list() -> None:
    """Print the current queue grouped by status."""
    entries = load_queue()
    if not entries:
        print("Review queue is empty. Run the mapper and enqueue proposals first.")
        return
    for status in ("pending", "approved"):
        group = [e for e in entries if e.get("status") == status]
        if not group:
            continue
        print(f"== {status.upper()} ({len(group)}) ==")
        for entry in group:
            evidence = ", ".join(entry.get("evidence_ids") or []) or "(no mapping)"
            line = f"  {entry['control_id']:<8} {entry['confidence']:<6} {evidence}"
            if status == "approved":
                line += f"  ({entry.get('reviewer')} @ {entry.get('decided_at')})"
            print(line)


def main() -> None:
    """Command-line entry point for inspecting and approving the queue."""
    parser = argparse.ArgumentParser(
        description="Human approval queue for evidence-to-control mappings.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the current queue grouped by status")

    approve_parser = sub.add_parser("approve", help="approve a pending mapping")
    approve_parser.add_argument("control_id", help="control id to approve, e.g. CC6.1")
    approve_parser.add_argument(
        "--reviewer", required=True, help="identifier of the approving human"
    )

    args = parser.parse_args()
    if args.command == "list":
        _cmd_list()
    elif args.command == "approve":
        approve(args.control_id, args.reviewer)
        print(f"Approved {args.control_id} (reviewer: {args.reviewer}).")


if __name__ == "__main__":
    main()

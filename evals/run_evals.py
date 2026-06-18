"""Evaluation harness: score agent mappings against the golden set.

Compares the agent's proposed mappings to the hand-labeled ground truth in
``evals/golden.yaml`` and reports precision/recall per control. Results are both
printed and written to ``evals/results.md``.

This is plain Python: a deterministic set comparison of the agent's proposed
mappings against a human-authored answer key. It is not an agent, makes no
Anthropic API call, and imports nothing from ``agent/``. No model judges a
model.

The two inputs are read-only here:

- ``evals/golden.yaml`` is human-authored ground truth and must never be written
  by code. It is also the authoritative list of controls (the spine of the run).
- ``evals/agent_mappings.json`` is the mapper's raw proposals, written by
  ``run.py`` and regenerable. If it is missing, this harness tells the operator
  to run ``run.py`` first and exits non-zero rather than fabricating it.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from typing import Any

import yaml

GOLDEN_PATH = "evals/golden.yaml"
AGENT_MAPPINGS_PATH = "evals/agent_mappings.json"
RESULTS_PATH = "evals/results.md"

# Verdict labels. Kept as named constants so stdout and results.md stay in sync
# and remain deterministic.
VERDICT_MATCH_EMPTY = "match (correct empty)"
VERDICT_EXACT = "exact match"
VERDICT_OVER_MAPPED = "precision miss (over-mapped)"
VERDICT_PRECISION = "precision miss"
VERDICT_RECALL = "recall miss"
VERDICT_MIXED = "mixed"


def load_golden() -> dict[str, list[str]]:
    """Load the hand-labeled ground truth (read-only).

    Reads ``evals/golden.yaml`` and returns the expected evidence per control,
    preserving file order so the golden set is the authoritative control spine
    for the run. This function only reads the file; it never writes to it.

    Returns:
        An ordered mapping of ``control_id`` to its list of expected evidence
        IDs (possibly empty).
    """
    with open(GOLDEN_PATH, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    golden: dict[str, list[str]] = {}
    for entry in data["golden"]:
        control_id = entry["control_id"]
        expected = entry.get("expected_evidence") or []
        golden[control_id] = list(expected)
    return golden


def load_agent_mappings() -> dict[str, list[str]]:
    """Load the agent's proposed mappings from ``evals/agent_mappings.json``.

    The file is a JSON list of objects shaped like the mapper's proposals
    (``{control_id, evidence_ids, confidence, rationale}``); only ``control_id``
    and ``evidence_ids`` are used here. If the file is absent, the operator is
    told to run ``run.py`` first and the process exits non-zero rather than
    fabricating predictions.

    Returns:
        A mapping of ``control_id`` to the agent's list of proposed evidence
        IDs.
    """
    if not os.path.exists(AGENT_MAPPINGS_PATH):
        print(
            f"{AGENT_MAPPINGS_PATH} not found. Run run.py first to generate the "
            "agent's mappings, then re-run the evals.",
            file=sys.stderr,
        )
        sys.exit(1)
    with open(AGENT_MAPPINGS_PATH, encoding="utf-8") as handle:
        records = json.load(handle)
    predicted: dict[str, list[str]] = {}
    for record in records:
        predicted[record["control_id"]] = list(record.get("evidence_ids") or [])
    return predicted


def score(
    predicted: dict[str, list[str]],
    golden: dict[str, list[str]],
) -> dict[str, dict[str, Any]]:
    """Compute precision/recall per control by deterministic set comparison.

    Iterates the controls in ``golden`` (the authoritative list). For each
    control, the agent's evidence is looked up by ``control_id``; a control
    absent from ``predicted`` is treated as an empty set (no mapping). Evidence
    is compared as sets of ID strings.

    Per control: ``TP = agent and golden``, ``FP = agent minus golden``,
    ``FN = golden minus agent``. Precision is ``TP / (TP + FP)`` and recall is
    ``TP / (TP + FN)``. Zero-denominator conventions:

    - golden empty and agent empty: precision 1.0, recall 1.0, verdict
      "match (correct empty)".
    - golden empty and agent non-empty: every agent item is a FP, precision 0.0,
      recall 1.0, verdict "precision miss (over-mapped)".
    - golden non-empty and agent empty: precision 1.0, recall 0.0, verdict
      "recall miss".
    - otherwise compute normally; verdict "exact match" if FP and FN are both
      empty, else "precision miss" / "recall miss" / "mixed".

    Args:
        predicted: The agent's proposed evidence IDs keyed by control id.
        golden: Ground-truth expected evidence IDs keyed by control id.

    Returns:
        A mapping keyed by control id. Each value holds ``tp``, ``fp``, ``fn``
        (sorted ID lists), ``precision``, ``recall``, and ``verdict``.
    """
    results: dict[str, dict[str, Any]] = {}
    for control_id, expected in golden.items():
        golden_set = set(expected)
        agent_set = set(predicted.get(control_id, []))

        tp = golden_set & agent_set
        fp = agent_set - golden_set
        fn = golden_set - agent_set

        if not golden_set and not agent_set:
            precision, recall, verdict = 1.0, 1.0, VERDICT_MATCH_EMPTY
        elif not golden_set:
            # golden empty, agent non-empty: everything is a false positive.
            precision, recall, verdict = 0.0, 1.0, VERDICT_OVER_MAPPED
        elif not agent_set:
            # golden non-empty, agent empty: pure recall miss.
            precision, recall, verdict = 1.0, 0.0, VERDICT_RECALL
        else:
            precision = len(tp) / (len(tp) + len(fp))
            recall = len(tp) / (len(tp) + len(fn))
            if not fp and not fn:
                verdict = VERDICT_EXACT
            elif fp and fn:
                verdict = VERDICT_MIXED
            elif fp:
                verdict = VERDICT_PRECISION
            else:
                verdict = VERDICT_RECALL

        results[control_id] = {
            "tp": sorted(tp),
            "fp": sorted(fp),
            "fn": sorted(fn),
            "precision": precision,
            "recall": recall,
            "verdict": verdict,
        }
    return results


def _aggregate(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compute micro-averaged precision/recall and the exact-match count.

    Micro-average sums true/false positives and negatives across all controls
    before dividing, so larger controls weigh proportionally. The exact-match
    count is the number of controls where the agent's set equals the golden set
    (verdicts "exact match" and "match (correct empty)").

    Args:
        results: The per-control output of :func:`score`.

    Returns:
        A mapping with ``precision``, ``recall``, ``exact_match``, and
        ``total`` keys.
    """
    sum_tp = sum(len(r["tp"]) for r in results.values())
    sum_fp = sum(len(r["fp"]) for r in results.values())
    sum_fn = sum(len(r["fn"]) for r in results.values())

    precision = sum_tp / (sum_tp + sum_fp) if (sum_tp + sum_fp) else 1.0
    recall = sum_tp / (sum_tp + sum_fn) if (sum_tp + sum_fn) else 1.0
    exact_match = sum(
        1
        for r in results.values()
        if r["verdict"] in (VERDICT_EXACT, VERDICT_MATCH_EMPTY)
    )

    return {
        "precision": precision,
        "recall": recall,
        "exact_match": exact_match,
        "total": len(results),
    }


def _table_rows(results: dict[str, dict[str, Any]]) -> list[list[str]]:
    """Build the per-control table rows shared by stdout and results.md.

    Args:
        results: The per-control output of :func:`score`.

    Returns:
        A list of string rows: control id, TP/FP/FN counts, precision, recall,
        and verdict.
    """
    rows: list[list[str]] = []
    for control_id, r in results.items():
        rows.append(
            [
                control_id,
                str(len(r["tp"])),
                str(len(r["fp"])),
                str(len(r["fn"])),
                f"{r['precision']:.2f}",
                f"{r['recall']:.2f}",
                r["verdict"],
            ]
        )
    return rows


_HEADERS = ["control", "TP", "FP", "FN", "precision", "recall", "verdict"]


def _print_report(
    results: dict[str, dict[str, Any]],
    aggregate: dict[str, Any],
) -> None:
    """Print the aggregate summary and per-control table to stdout.

    Args:
        results: The per-control output of :func:`score`.
        aggregate: The output of :func:`_aggregate`.
    """
    rows = _table_rows(results)
    widths = [
        max(len(_HEADERS[i]), *(len(row[i]) for row in rows))
        for i in range(len(_HEADERS))
    ]

    def fmt(cells: list[str]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells))

    print(
        f"micro precision {aggregate['precision']:.2f}  "
        f"micro recall {aggregate['recall']:.2f}  "
        f"exact match {aggregate['exact_match']}/{aggregate['total']}"
    )
    print()
    print(fmt(_HEADERS))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt(row))


def _render_results_md(
    results: dict[str, dict[str, Any]],
    aggregate: dict[str, Any],
    timestamp: str,
) -> str:
    """Render the durable results.md record as a Markdown string.

    The output is employer-generic and neutral: no job-search, company, or
    candidate references. Only the timestamp line varies between runs on
    identical inputs.

    Args:
        results: The per-control output of :func:`score`.
        aggregate: The output of :func:`_aggregate`.
        timestamp: A UTC timestamp string for the run header.

    Returns:
        The full Markdown document.
    """
    lines: list[str] = []
    lines.append("# Evaluation results")
    lines.append("")
    lines.append(f"Run: {timestamp}")
    lines.append("")
    lines.append("## Aggregate")
    lines.append("")
    lines.append(f"- micro precision: {aggregate['precision']:.2f}")
    lines.append(f"- micro recall: {aggregate['recall']:.2f}")
    lines.append(
        f"- exact match: {aggregate['exact_match']}/{aggregate['total']}"
    )
    lines.append("")
    lines.append("## Per-control")
    lines.append("")
    lines.append("| " + " | ".join(_HEADERS) + " |")
    lines.append("| " + " | ".join("---" for _ in _HEADERS) + " |")
    for row in _table_rows(results):
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("## Misses")
    lines.append("")

    miss_controls = [
        (control_id, r)
        for control_id, r in results.items()
        if r["fp"] or r["fn"]
    ]
    if not miss_controls:
        lines.append("None. Every control matched the golden set exactly.")
    else:
        for control_id, r in miss_controls:
            lines.append(f"### {control_id}")
            lines.append("")
            lines.append(f"- verdict: {r['verdict']}")
            fp_value = ", ".join(r["fp"]) if r["fp"] else "none"
            fn_value = ", ".join(r["fn"]) if r["fn"] else "none"
            lines.append(f"- false positives (FP): {fp_value}")
            lines.append(f"- false negatives (FN): {fn_value}")
            lines.append("")

    # Ensure a single trailing newline for a stable, deterministic file.
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> None:
    """Run the evaluation end to end: load, score, print, and write results.

    Loads the golden set and the agent's mappings (exiting non-zero if the
    mappings file is absent), scores them by deterministic set comparison,
    prints a per-control report to stdout, and writes ``evals/results.md``.
    """
    golden = load_golden()
    predicted = load_agent_mappings()
    results = score(predicted, golden)
    aggregate = _aggregate(results)

    _print_report(results, aggregate)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    with open(RESULTS_PATH, "w", encoding="utf-8") as handle:
        handle.write(_render_results_md(results, aggregate, timestamp))
    print()
    print(f"Wrote {RESULTS_PATH}")


if __name__ == "__main__":
    main()

"""End-to-end orchestrator for the GRC evidence pipeline.

Runs the full v1 pipeline in one shot:

    1. Load ``.env`` (collectors need ``GITHUB_PAT``; the mapper needs
       ``ANTHROPIC_API_KEY``).
    2. Load the controls from ``controls.yaml``.
    3. Collect evidence from the live GitHub collector and the mock AWS
       collector, combined into one list.
    4. Persist the combined inventory to ``evidence_inventory.json``: the
       lookup that resolves an evidence id in ``REVIEW.md`` back to its source,
       type, raw content, and collection time.
    5. Ask the mapper to propose evidence-to-control mappings. The mapper owns
       its model configuration; this orchestrator never overrides it.
    6. Write the raw proposed mappings to ``evals/agent_mappings.json``: the
       agent's unfiltered proposals, the input the eval scores against the
       golden set, independent of any later human approval.
    7. Enqueue the proposals into the human approval queue as ``pending``.
    8. Print a run summary.

This module never accepts a mapping: it only enqueues proposals as ``pending``.
Approval happens exclusively through :mod:`approve`.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from typing import Any

import yaml
from dotenv import load_dotenv

import approve
from agent.mapper import Mapping, map_evidence_to_controls
from collectors.aws_mock_collector import collect_aws_evidence
from collectors.github_collector import collect_github_evidence
from evidence import Evidence

CONTROLS_PATH = "controls.yaml"
INVENTORY_PATH = "evidence_inventory.json"
AGENT_MAPPINGS_PATH = "evals/agent_mappings.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the pipeline run.

    The GitHub target repository is taken from ``--owner``/``--repo`` when
    given, falling back to the ``GITHUB_OWNER``/``GITHUB_REPO`` environment
    variables. ``.env`` is loaded before this fallback is read so the variables
    may live in the gitignored ``.env`` alongside the secrets.

    Args:
        argv: Argument list to parse (defaults to ``sys.argv[1:]``).

    Returns:
        The parsed arguments namespace with ``owner`` and ``repo`` attributes.
    """
    parser = argparse.ArgumentParser(
        description="Run the full GRC evidence pipeline end to end.",
    )
    parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner (org or user) of the target repo. Falls back to "
        "the GITHUB_OWNER env var.",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="GitHub repository name. Falls back to the GITHUB_REPO env var.",
    )
    return parser.parse_args(argv)


def resolve_target(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve the GitHub owner/repo from CLI args, then the environment.

    Args:
        args: Parsed CLI arguments (``owner``/``repo``, each possibly ``None``).

    Returns:
        A ``(owner, repo)`` tuple.

    Raises:
        SystemExit: If either value is missing from both the CLI and the
            environment.
    """
    owner = args.owner or os.environ.get("GITHUB_OWNER", "").strip()
    repo = args.repo or os.environ.get("GITHUB_REPO", "").strip()
    missing = [
        name
        for name, value in (("owner", owner), ("repo", repo))
        if not value
    ]
    if missing:
        raise SystemExit(
            "Missing GitHub target: "
            + ", ".join(missing)
            + ". Pass --owner/--repo or set GITHUB_OWNER/GITHUB_REPO in .env."
        )
    return owner, repo


def load_controls(path: str = CONTROLS_PATH) -> list[dict[str, Any]]:
    """Load the control definitions from ``controls.yaml``.

    Args:
        path: Path to the controls YAML file, relative to the repo root.

    Returns:
        The list of control dicts (each with at least ``id``, ``description``,
        and ``expected_evidence``), in file order.

    Raises:
        RuntimeError: If the file is missing, is not valid YAML, or does not
            contain a ``controls`` list.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            parsed = yaml.safe_load(handle)
    except FileNotFoundError as exc:
        raise RuntimeError(f"controls file not found at '{path}'.") from exc
    except yaml.YAMLError as exc:
        raise RuntimeError(f"controls file '{path}' is not valid YAML: {exc}.") from exc

    controls = parsed.get("controls") if isinstance(parsed, dict) else None
    if not isinstance(controls, list) or not controls:
        raise RuntimeError(
            f"controls file '{path}' must contain a non-empty 'controls' list."
        )
    return controls


def collect_all_evidence(owner: str, repo: str) -> list[Evidence]:
    """Collect and combine evidence from every v1 source.

    Args:
        owner: GitHub owner (org or user) of the target repo.
        repo: GitHub repository name.

    Returns:
        The combined evidence list: GitHub evidence followed by AWS mock
        evidence, each in its collector's stable order.
    """
    github_evidence = collect_github_evidence(owner, repo)
    aws_evidence = collect_aws_evidence()
    return github_evidence + aws_evidence


def write_inventory(evidence: list[Evidence], path: str = INVENTORY_PATH) -> None:
    """Persist the combined evidence inventory as JSON.

    Writes one record per evidence item with the full schema
    ``{id, source, type, raw, collected_at}``. This is the lookup ``REVIEW.md``
    uses to resolve an evidence id back to its source, type, raw content, and
    collection time. The file is regenerated each run.

    Args:
        evidence: The combined evidence list to persist.
        path: Output path, relative to the repo root.
    """
    records = [dataclasses.asdict(item) for item in evidence]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2, default=str)
        handle.write("\n")


def write_agent_mappings(
    mappings: list[Mapping], path: str = AGENT_MAPPINGS_PATH
) -> None:
    """Persist the agent's raw proposed mappings as JSON.

    Writes each mapping exactly as the mapper returned it
    (``{control_id, evidence_ids, confidence, rationale}``). This is the eval's
    input, so it must be the agent's unfiltered proposals, independent of any
    later human approval recorded in the review queue.

    Args:
        mappings: The proposals returned by the mapper, in control order.
        path: Output path, relative to the repo root.
    """
    records = [dataclasses.asdict(mapping) for mapping in mappings]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(records, handle, indent=2)
        handle.write("\n")


def print_summary(
    owner: str,
    repo: str,
    evidence: list[Evidence],
    controls: list[dict[str, Any]],
    mappings: list[Mapping],
) -> None:
    """Print a human-readable summary of the completed run.

    Reports evidence collected per source, controls assessed, mappings
    proposed (those with at least one cited evidence id), and the path of every
    file written.

    Args:
        owner: The GitHub owner the run targeted.
        repo: The GitHub repository the run targeted.
        evidence: The combined evidence collected.
        controls: The controls assessed.
        mappings: The proposals returned by the mapper.
    """
    per_source: dict[str, int] = {}
    for item in evidence:
        per_source[item.source] = per_source.get(item.source, 0) + 1

    proposed = sum(1 for m in mappings if m.evidence_ids)

    print("GRC evidence pipeline: run complete")
    print(f"  Target repo:          {owner}/{repo}")
    print("  Evidence collected:")
    for source in sorted(per_source):
        print(f"    - {source}: {per_source[source]}")
    print(f"    - total: {len(evidence)}")
    print(f"  Controls assessed:    {len(controls)}")
    print(f"  Mappings proposed:    {proposed} (of {len(mappings)} controls)")
    print("  Files written:")
    print(f"    - {INVENTORY_PATH}")
    print(f"    - {AGENT_MAPPINGS_PATH}")
    print(f"    - {approve.QUEUE_PATH}")
    print(f"    - {approve.REVIEW_MD_PATH}")
    print(
        "  Nothing is accepted: all proposals are queued as pending. "
        f"Review in {approve.REVIEW_MD_PATH}, approve via approve.py."
    )


def main(argv: list[str] | None = None) -> None:
    """Run the full evidence pipeline end to end.

    Args:
        argv: Argument list to parse (defaults to ``sys.argv[1:]``).
    """
    load_dotenv()  # collectors read GITHUB_PAT, mapper reads ANTHROPIC_API_KEY
    args = parse_args(argv)
    owner, repo = resolve_target(args)

    controls = load_controls()
    evidence = collect_all_evidence(owner, repo)
    write_inventory(evidence)

    mappings = map_evidence_to_controls(evidence, controls)
    write_agent_mappings(mappings)
    approve.enqueue_pending(mappings)

    print_summary(owner, repo, evidence, controls, mappings)


if __name__ == "__main__":
    main()

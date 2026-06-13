"""Shared Evidence schema for the GRC evidence agent.

Every collector emits, and the mapper consumes, objects shaped exactly like
:class:`Evidence`. This is the single canonical definition referenced by
CLAUDE.md ("Evidence schema everywhere: {id, source, type, raw, collected_at}").
Keep this module dependency-light so both collectors and the agent can import it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Evidence:
    """A single piece of collected evidence.

    Attributes:
        id: Stable, unique identifier for this evidence item (e.g.
            "github.branch_protection.main").
        source: Originating collector namespace, e.g. "github" or "aws".
        type: Evidence type matching the vocabulary in controls.yaml, e.g.
            "github.branch_protection" or "aws.iam_password_policy".
        raw: The raw payload as returned by the source, preserved verbatim so
            a human reviewer can audit the mapping.
        collected_at: ISO-8601 UTC timestamp of when the evidence was collected.
    """

    id: str
    source: str
    type: str
    raw: dict[str, Any]
    collected_at: str

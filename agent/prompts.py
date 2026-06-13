"""Versioned prompt templates for the GRC evidence agent.

This module is the *only* place prompt text lives. No inline prompts elsewhere —
callers (e.g. :mod:`agent.mapper`) import templates from here so prompt changes
are reviewable and versioned. When a template changes meaningfully, bump
``PROMPT_VERSION`` and add a new constant rather than mutating the old one.

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

PROMPT_VERSION = "v1"

# System/instruction template for the evidence-to-control mapping task. The
# mapper formats this with the controls and collected evidence and expects a
# JSON response shaped {control_id, evidence_ids[], confidence, rationale}.
# Stub only — final wording to be authored during implementation.
MAPPING_PROMPT_V1 = ""

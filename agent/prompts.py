"""Versioned prompt templates for the GRC evidence agent.

This module is the *only* place prompt text lives. No inline prompts elsewhere —
callers (e.g. :mod:`agent.mapper`) import templates from here so prompt changes
are reviewable and versioned. When a template changes meaningfully, bump
``PROMPT_VERSION`` and add a new constant rather than mutating the old one.
"""

from __future__ import annotations

import json
from typing import Any

from evidence import Evidence

PROMPT_VERSION = "v1"

# System/instruction template for the evidence-to-control mapping task. Sent as
# the ``system`` prompt; it operationalizes the confidence criteria documented on
# :class:`agent.mapper.Mapping` and the project's "propose no mapping rather than
# a low-confidence stretch" restraint rule.
MAPPING_SYSTEM_V1 = """\
You are a GRC evidence-mapping assistant for a SOC 2 readiness review. Given one
control and a list of collected evidence items, you decide which evidence (if
any) supports that control. You only propose mappings; a human reviewer approves
them, so accuracy and restraint matter more than coverage.

Confidence criteria:
- high: an evidence item's type matches the control's expected evidence AND its
  raw content confirms the control is configured or operating as intended.
- medium: evidence is relevant but only partially satisfies the control, or
  satisfies it with a caveat or gap.
- low: evidence is tangentially related or weakly suggestive and would not stand
  alone in an assessment.

Restraint:
- If no collected evidence genuinely addresses the control, return an empty
  evidence_ids array. Do NOT manufacture a low-confidence stretch to fill a gap.
  Some controls are intentionally not evidenced by the available sources, and
  proposing no mapping is the correct answer for them.
- When you return an empty evidence_ids array, set confidence to "low".
- Base every decision only on the evidence provided. Never invent evidence ids.

Respond with a single JSON object matching the required schema and nothing else.
"""

# User-message template. Formatted per control by :func:`render_mapping_prompt`
# with that control's definition and the full collected-evidence list.
MAPPING_USER_TEMPLATE_V1 = """\
Assess a single SOC 2 control against the collected evidence.

CONTROL
  id: {control_id}
  name: {control_name}
  description: {control_description}
  expected_evidence_types: {expected_evidence}

COLLECTED EVIDENCE (JSON array; map only against these items):
{evidence_json}

Decide which evidence items, if any, satisfy this control. Return a single JSON
object with keys: control_id, evidence_ids, confidence, rationale.
- control_id MUST equal "{control_id}".
- evidence_ids MUST be a subset of the "id" values in the evidence array above.
- If no collected evidence genuinely addresses this control, return an empty
  evidence_ids array rather than forcing a weak match.
"""

# Appended as a corrective user turn when the first response fails validation.
# Formatted with the validation error so the model can self-correct exactly once.
MAPPING_RETRY_INSTRUCTION_V1 = """\
Your previous response was not accepted: {error}

Respond again with ONLY the JSON object matching the required schema
(control_id, evidence_ids, confidence, rationale). Use the control_id exactly as
given, reference only evidence ids present in the evidence list, and use an empty
evidence_ids array if nothing genuinely applies.
"""

# JSON Schema for structured outputs (output_config.format). Constrains the model
# to the {control_id, evidence_ids[], confidence, rationale} shape.
MAPPING_OUTPUT_SCHEMA_V1: dict[str, Any] = {
    "type": "object",
    "properties": {
        "control_id": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
        "rationale": {"type": "string"},
    },
    "required": ["control_id", "evidence_ids", "confidence", "rationale"],
    "additionalProperties": False,
}


def render_mapping_prompt(
    control: dict[str, Any],
    evidence: list[Evidence],
) -> str:
    """Render the per-control user prompt for the mapping task.

    Args:
        control: A parsed control definition from ``controls.yaml`` (expects at
            least ``id``; ``name``, ``description``, and ``expected_evidence``
            are used when present).
        evidence: All collected evidence to offer the model for this control.

    Returns:
        The formatted user-message string built from
        :data:`MAPPING_USER_TEMPLATE_V1`, with the full evidence list serialized
        as a JSON array.
    """
    evidence_payload = [
        {
            "id": item.id,
            "source": item.source,
            "type": item.type,
            "raw": item.raw,
            "collected_at": item.collected_at,
        }
        for item in evidence
    ]
    description = " ".join(str(control.get("description", "")).split())
    return MAPPING_USER_TEMPLATE_V1.format(
        control_id=control["id"],
        control_name=control.get("name", ""),
        control_description=description,
        expected_evidence=json.dumps(control.get("expected_evidence", [])),
        evidence_json=json.dumps(evidence_payload, indent=2, default=str),
    )

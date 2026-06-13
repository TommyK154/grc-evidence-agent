"""Evidence-to-control mapper backed by the Claude API.

Given collected :class:`~evidence.Evidence` and the parsed controls, the mapper
asks Claude to propose which evidence satisfies which control. The model is
prompted (templates live in :mod:`agent.prompts`) to return structured JSON of
the form ``{control_id, evidence_ids[], confidence, rationale}``. The output is
validated against the :class:`Mapping` schema; on malformed output the call is
retried once before failing.

Nothing here accepts a mapping — proposals flow to the human approval queue in
:mod:`approve`.

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from evidence import Evidence


@dataclass
class Mapping:
    """A proposed mapping of evidence to a single control.

    Attributes:
        control_id: The control this mapping addresses, e.g. "CC6.1".
        evidence_ids: IDs of the :class:`Evidence` items that satisfy the
            control. Empty when the agent proposes no mapping (correct behavior
            for evidence-poor controls such as CC7.3).
        confidence: Rating of how well the cited evidence supports the control,
            one of "high", "medium", or "low". Canonical criteria:

            - high: evidence type matches the control's expected evidence AND
              the raw content confirms the control is configured or operating
              as intended.
            - medium: evidence is relevant but only partially satisfies the
              control, or satisfies it with a caveat or gap.
            - low: evidence is tangentially related or weakly suggestive; would
              not stand alone in an assessment.
            - If no collected evidence addresses a control, propose NO mapping
              (empty evidence_ids) rather than a low-confidence stretch. This is
              the correct behavior for evidence-poor controls.

        rationale: Short natural-language justification for the mapping.

    The MAPPING_PROMPT_V1 template in :mod:`agent.prompts` will operationalize
    these criteria when the mapper is implemented.
    """

    control_id: str
    evidence_ids: list[str]
    confidence: Literal["high", "medium", "low"]
    rationale: str


def map_evidence_to_controls(
    evidence: list[Evidence],
    controls: list[dict[str, Any]],
) -> list[Mapping]:
    """Map collected evidence onto controls using the Claude API.

    Args:
        evidence: All evidence collected from the v1 sources.
        controls: Parsed control definitions from ``controls.yaml`` (each a dict
            with at least ``id``, ``description``, and ``expected_evidence``).

    Returns:
        One :class:`Mapping` proposal per control the agent chose to address.

    Raises:
        NotImplementedError: Always, until the mapper is implemented.
    """
    raise NotImplementedError


def _parse_and_validate(raw_response: str) -> list[Mapping]:
    """Parse the model's JSON response into validated :class:`Mapping` objects.

    Args:
        raw_response: The raw text returned by the Claude API.

    Returns:
        Validated mappings parsed from the response.

    Raises:
        NotImplementedError: Always, until the mapper is implemented.
    """
    raise NotImplementedError

"""Evidence-to-control mapper backed by the Claude API.

Given collected :class:`~evidence.Evidence` and the parsed controls, the mapper
asks Claude — once per control, with that control's definition and *all* the
collected evidence — to propose which evidence satisfies the control. Prompt
templates live in :mod:`agent.prompts`. The model is constrained via structured
outputs to return ``{control_id, evidence_ids[], confidence, rationale}``; each
response is validated against the :class:`Mapping` schema, and a malformed
response is retried exactly once before failing.

Nothing here accepts a mapping — proposals flow to the human approval queue in
:mod:`approve`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

import anthropic
from dotenv import load_dotenv

from agent import prompts
from evidence import Evidence

# Model + request settings. Sonnet 4.6 is a deliberate budget choice (the $5 API
# allowance must survive at least two full eval runs). No thinking parameter:
# effort and a tight max_tokens keep per-call token spend predictable; the
# mapping output is a single small JSON object.
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 1024
EFFORT = "medium"


class MappingValidationError(Exception):
    """Raised when a model response cannot be validated into a :class:`Mapping`."""


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

    The MAPPING_SYSTEM_V1 template in :mod:`agent.prompts` operationalizes these
    criteria for the model.
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

    Makes one API call per control, supplying that control's definition and the
    full evidence list. Returns one :class:`Mapping` per control; a mapping with
    an empty ``evidence_ids`` represents the agent correctly declining to map an
    evidence-poor control (e.g. CC7.3) and is preserved rather than dropped, so
    reviewers and evals can see the restraint decision explicitly.

    Args:
        evidence: All evidence collected from the v1 sources.
        controls: Parsed control definitions from ``controls.yaml`` (each a dict
            with at least ``id``, ``description``, and ``expected_evidence``).

    Returns:
        One :class:`Mapping` proposal per control, in ``controls`` order.

    Raises:
        MappingValidationError: If a control's mapping still fails validation
            after one retry.
    """
    load_dotenv()  # pick up ANTHROPIC_API_KEY from the gitignored .env
    client = anthropic.Anthropic()
    return [_map_single_control(client, control, evidence) for control in controls]


def _map_single_control(
    client: anthropic.Anthropic,
    control: dict[str, Any],
    evidence: list[Evidence],
) -> Mapping:
    """Request, validate, and (once) retry the mapping for a single control.

    Args:
        client: An initialized Anthropic API client.
        control: The control definition to assess.
        evidence: All collected evidence offered to the model.

    Returns:
        The validated :class:`Mapping` proposed for this control.

    Raises:
        MappingValidationError: If the response still fails validation after one
            corrective retry.
    """
    control_id = control["id"]
    valid_ids = {item.id for item in evidence}
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": prompts.render_mapping_prompt(control, evidence)}
    ]

    # First attempt.
    raw = _assistant_text(_call_model(client, messages))
    try:
        if raw is None:
            raise MappingValidationError("model refused or returned no text block")
        return _parse_and_validate(raw, control_id, valid_ids)
    except MappingValidationError as first_error:
        # Retry exactly once with the conversation
        # [user, assistant(bad response), user(retry instruction)] so the model
        # sees its own rejected output. The guard skips the assistant turn only
        # when there was no text to replay (a refusal/empty first response).
        if raw is not None:
            messages.append({"role": "assistant", "content": raw})
        messages.append(
            {
                "role": "user",
                "content": prompts.MAPPING_RETRY_INSTRUCTION_V1.format(error=first_error),
            }
        )
        retry_raw = _assistant_text(_call_model(client, messages))
        try:
            if retry_raw is None:
                raise MappingValidationError("model refused or returned no text block")
            return _parse_and_validate(retry_raw, control_id, valid_ids)
        except MappingValidationError as retry_error:
            raise MappingValidationError(
                f"mapping for control {control_id} failed validation after one "
                f"retry: {retry_error}"
            ) from retry_error


def _call_model(
    client: anthropic.Anthropic,
    messages: list[dict[str, Any]],
) -> Any:
    """Make one mapping API call with structured-output constraints.

    Args:
        client: An initialized Anthropic API client.
        messages: The conversation to send.

    Returns:
        The raw response object from ``client.messages.create``.
    """
    return client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=prompts.MAPPING_SYSTEM_V1,
        messages=messages,
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": prompts.MAPPING_OUTPUT_SCHEMA_V1},
        },
    )


def _assistant_text(response: Any) -> str | None:
    """Extract the assistant's JSON text from a Claude response.

    Args:
        response: The object returned by ``client.messages.create``.

    Returns:
        The text of the first text content block, or ``None`` if the model
        refused or returned no text block (so the caller can still retry).
    """
    if getattr(response, "stop_reason", None) == "refusal":
        return None
    return next(
        (block.text for block in response.content if block.type == "text"),
        None,
    )


def _parse_and_validate(
    raw_response: str,
    control_id: str,
    valid_ids: set[str],
) -> Mapping:
    """Parse the model's JSON response into a validated :class:`Mapping`.

    Args:
        raw_response: The raw text returned by the Claude API.
        control_id: The control id the response must address.
        valid_ids: The set of evidence ids the response may reference.

    Returns:
        A validated :class:`Mapping`.

    Raises:
        MappingValidationError: If the response is not valid JSON, has the wrong
            shape, names the wrong control, references unknown evidence ids, or
            carries an invalid confidence/rationale.
    """
    try:
        data = json.loads(raw_response)
    except (json.JSONDecodeError, TypeError) as exc:
        raise MappingValidationError(f"response was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise MappingValidationError(
            f"expected a JSON object, got {type(data).__name__}"
        )

    returned_id = data.get("control_id")
    if returned_id != control_id:
        raise MappingValidationError(
            f"control_id mismatch: expected {control_id!r}, got {returned_id!r}"
        )

    confidence = data.get("confidence")
    if confidence not in ("high", "medium", "low"):
        raise MappingValidationError(f"invalid confidence: {confidence!r}")

    evidence_ids = data.get("evidence_ids")
    if not isinstance(evidence_ids, list) or not all(
        isinstance(eid, str) for eid in evidence_ids
    ):
        raise MappingValidationError("evidence_ids must be a list of strings")

    unknown = [eid for eid in evidence_ids if eid not in valid_ids]
    if unknown:
        raise MappingValidationError(f"references unknown evidence ids: {unknown}")

    rationale = data.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise MappingValidationError("rationale must be a non-empty string")

    return Mapping(
        control_id=control_id,
        evidence_ids=evidence_ids,
        confidence=confidence,
        rationale=rationale.strip(),
    )

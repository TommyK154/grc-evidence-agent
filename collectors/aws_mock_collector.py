"""Mock AWS evidence collector.

Reads ``data/sample_aws_config.json`` and normalizes it into the shared
:class:`~evidence.Evidence` schema. The mock keeps the demo reproducible: it
produces the same AWS-shaped evidence every run without live credentials.

Signals produced in v1 (evidence ``type`` -> controls.yaml vocabulary):
    - aws.iam_password_policy
    - aws.cloudtrail_enabled
    - aws.s3_public_access_block
    - aws.root_mfa

Per the project's design principles, this collector never auto-judges: it
records what the config reports (the verbatim section is preserved in the
``raw`` payload) and a plain-English ``note`` of fact, leaving the pass/fail
control judgment to the agent and the human approval queue. A missing config
section is captured as evidence with ``data=None`` rather than crashing; only a
missing or malformed config file aborts collection.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from evidence import Evidence

SOURCE = "aws"
DEFAULT_CONFIG_PATH = "data/sample_aws_config.json"


def _now() -> str:
    """Return the current UTC time as an ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _evidence(
    *,
    account_id: str | None,
    generated_at: str | None,
    source_file: str,
    evidence_type: str,
    data: Any,
    note: str,
) -> Evidence:
    """Build an :class:`Evidence` item with the standard mock ``raw`` envelope.

    The evidence ``id`` is account-scoped (``{type}.{account_id}``) so it stays
    stable and unique across accounts, mirroring the GitHub collector's
    branch/repo scoping. ``collected_at`` is the config's ``generated_at``
    snapshot time (falling back to wall-clock only if the config omits it), which
    keeps repeated mock runs byte-identical.

    Args:
        account_id: AWS account the evidence pertains to (may be ``None`` if the
            config omits it).
        generated_at: The config's snapshot timestamp, used as ``collected_at``.
        source_file: Path of the config file the evidence was read from.
        evidence_type: Evidence ``type`` matching the controls.yaml vocabulary.
        data: The verbatim config section (or ``None`` when the section is
            absent), preserved for human audit.
        note: A plain-English, factual description of what the config reports.

    Returns:
        The normalized :class:`Evidence` item.
    """
    scope = account_id if account_id else "unknown"
    return Evidence(
        id=f"{evidence_type}.{scope}",
        source=SOURCE,
        type=evidence_type,
        raw={
            "source_file": source_file,
            "account_id": account_id,
            "generated_at": generated_at,
            "data": data,
            "note": note,
        },
        collected_at=generated_at or _now(),
    )


def _collect_iam_password_policy(
    config: dict[str, Any], source_file: str
) -> Evidence:
    """Normalize the IAM password policy section (aws.iam_password_policy).

    Args:
        config: The parsed sample AWS config.
        source_file: Path the config was read from (recorded in ``raw``).

    Returns:
        The IAM password policy :class:`Evidence`.
    """
    account_id = config.get("account_id")
    generated_at = config.get("generated_at")
    policy = config.get("iam_password_policy")

    if isinstance(policy, dict):
        note = (
            "IAM password policy present: minimum length "
            f"{policy.get('MinimumPasswordLength')}, "
            f"reuse prevention {policy.get('PasswordReusePrevention')}, "
            f"max age {policy.get('MaxPasswordAge')} days."
        )
    else:
        note = "no iam_password_policy section in config."

    return _evidence(
        account_id=account_id,
        generated_at=generated_at,
        source_file=source_file,
        evidence_type="aws.iam_password_policy",
        data=policy if isinstance(policy, dict) else None,
        note=note,
    )


def _collect_cloudtrail(config: dict[str, Any], source_file: str) -> Evidence:
    """Normalize the CloudTrail section (aws.cloudtrail_enabled).

    Args:
        config: The parsed sample AWS config.
        source_file: Path the config was read from (recorded in ``raw``).

    Returns:
        The CloudTrail :class:`Evidence`.
    """
    account_id = config.get("account_id")
    generated_at = config.get("generated_at")
    trail = config.get("cloudtrail")

    if isinstance(trail, dict):
        note = (
            f"CloudTrail '{trail.get('TrailName')}' is_logging="
            f"{trail.get('IsLogging')}, multi_region="
            f"{trail.get('IsMultiRegionTrail')}, log_file_validation="
            f"{trail.get('LogFileValidationEnabled')}."
        )
    else:
        note = "no cloudtrail section in config."

    return _evidence(
        account_id=account_id,
        generated_at=generated_at,
        source_file=source_file,
        evidence_type="aws.cloudtrail_enabled",
        data=trail if isinstance(trail, dict) else None,
        note=note,
    )


def _collect_s3_public_access_block(
    config: dict[str, Any], source_file: str
) -> Evidence:
    """Normalize the S3 public access block section (aws.s3_public_access_block).

    Args:
        config: The parsed sample AWS config.
        source_file: Path the config was read from (recorded in ``raw``).

    Returns:
        The S3 public access block :class:`Evidence`.
    """
    account_id = config.get("account_id")
    generated_at = config.get("generated_at")
    block = config.get("s3_public_access_block")

    if isinstance(block, dict):
        note = (
            f"S3 public access block ({block.get('scope')}): "
            f"BlockPublicAcls={block.get('BlockPublicAcls')}, "
            f"IgnorePublicAcls={block.get('IgnorePublicAcls')}, "
            f"BlockPublicPolicy={block.get('BlockPublicPolicy')}, "
            f"RestrictPublicBuckets={block.get('RestrictPublicBuckets')}."
        )
    else:
        note = "no s3_public_access_block section in config."

    return _evidence(
        account_id=account_id,
        generated_at=generated_at,
        source_file=source_file,
        evidence_type="aws.s3_public_access_block",
        data=block if isinstance(block, dict) else None,
        note=note,
    )


def _collect_root_mfa(config: dict[str, Any], source_file: str) -> Evidence:
    """Normalize the root account section (aws.root_mfa).

    Args:
        config: The parsed sample AWS config.
        source_file: Path the config was read from (recorded in ``raw``).

    Returns:
        The root MFA :class:`Evidence`.
    """
    account_id = config.get("account_id")
    generated_at = config.get("generated_at")
    root = config.get("root_account")

    if isinstance(root, dict):
        note = (
            f"root MFA enabled={root.get('RootUserMfaEnabled')}, "
            f"root access keys present={root.get('RootUserAccessKeysPresent')}."
        )
    else:
        note = "no root_account section in config."

    return _evidence(
        account_id=account_id,
        generated_at=generated_at,
        source_file=source_file,
        evidence_type="aws.root_mfa",
        data=root if isinstance(root, dict) else None,
        note=note,
    )


def collect_aws_evidence(config_path: str = DEFAULT_CONFIG_PATH) -> list[Evidence]:
    """Collect AWS evidence from the sample config file.

    Reads the mock config once and normalizes its four v1 signal sections into
    the shared :class:`Evidence` schema. Returns evidence in a stable order so
    repeated runs are reproducible.

    Args:
        config_path: Path to the sample AWS config JSON, relative to repo root.

    Returns:
        A list of :class:`Evidence` items, one per AWS signal, in the order:
        iam_password_policy, cloudtrail_enabled, s3_public_access_block,
        root_mfa.

    Raises:
        RuntimeError: If the config file is missing or is not valid JSON (a
            config error, not a control finding).
    """
    try:
        with open(config_path, encoding="utf-8") as handle:
            config = json.load(handle)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"AWS mock config not found at '{config_path}'. Expected the sample "
            "config to exist (see data/sample_aws_config.json)."
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"AWS mock config at '{config_path}' is not valid JSON: {exc}."
        ) from exc

    if not isinstance(config, dict):
        raise RuntimeError(
            f"AWS mock config at '{config_path}' must be a JSON object, got "
            f"{type(config).__name__}."
        )

    return [
        _collect_iam_password_policy(config, config_path),
        _collect_cloudtrail(config, config_path),
        _collect_s3_public_access_block(config, config_path),
        _collect_root_mfa(config, config_path),
    ]

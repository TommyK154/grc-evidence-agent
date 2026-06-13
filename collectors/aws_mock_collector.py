"""Mock AWS evidence collector.

Reads ``data/sample_aws_config.json`` and normalizes it into the shared
:class:`~evidence.Evidence` schema. The mock keeps the demo reproducible: it
produces the same AWS-shaped evidence every run without live credentials.

Signals produced in v1 (evidence ``type`` -> controls.yaml vocabulary):
    - aws.iam_password_policy
    - aws.cloudtrail_enabled
    - aws.s3_public_access_block
    - aws.root_mfa

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

from evidence import Evidence

DEFAULT_CONFIG_PATH = "data/sample_aws_config.json"


def collect_aws_evidence(config_path: str = DEFAULT_CONFIG_PATH) -> list[Evidence]:
    """Collect AWS evidence from the sample config file.

    Args:
        config_path: Path to the sample AWS config JSON, relative to repo root.

    Returns:
        A list of :class:`Evidence` items, one per AWS signal in the config.

    Raises:
        NotImplementedError: Always, until the collector is implemented.
    """
    raise NotImplementedError

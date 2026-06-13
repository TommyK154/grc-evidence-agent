"""Live GitHub evidence collector.

Pulls control-relevant signals from the GitHub API using a fine-grained PAT
read from the environment (see ``.env`` / ``.env.example``). Each signal is
normalized into the shared :class:`~evidence.Evidence` schema.

Signals collected in v1 (evidence ``type`` -> controls.yaml vocabulary):
    - github.branch_protection
    - github.required_reviews
    - github.two_factor_status
    - github.dependabot_status
    - github.dependabot_alerts
    - github.secret_scanning

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

from evidence import Evidence


def collect_github_evidence(owner: str, repo: str) -> list[Evidence]:
    """Collect all v1 GitHub evidence for a repository.

    Args:
        owner: GitHub organization or user that owns the repository.
        repo: Repository name.

    Returns:
        A list of :class:`Evidence` items, one per collected signal.

    Raises:
        NotImplementedError: Always, until the collector is implemented.
    """
    raise NotImplementedError


def _collect_branch_protection(owner: str, repo: str) -> Evidence:
    """Collect branch protection settings as evidence (github.branch_protection)."""
    raise NotImplementedError


def _collect_required_reviews(owner: str, repo: str) -> Evidence:
    """Collect required-review settings as evidence (github.required_reviews)."""
    raise NotImplementedError


def _collect_two_factor_status(owner: str) -> Evidence:
    """Collect org 2FA enforcement status as evidence (github.two_factor_status)."""
    raise NotImplementedError


def _collect_dependabot_status(owner: str, repo: str) -> Evidence:
    """Collect Dependabot enablement as evidence (github.dependabot_status)."""
    raise NotImplementedError


def _collect_dependabot_alerts(owner: str, repo: str) -> Evidence:
    """Collect open Dependabot alerts as evidence (github.dependabot_alerts)."""
    raise NotImplementedError


def _collect_secret_scanning(owner: str, repo: str) -> Evidence:
    """Collect secret-scanning status as evidence (github.secret_scanning)."""
    raise NotImplementedError

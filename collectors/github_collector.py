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

Branch protection is read from BOTH classic branch protection and repository
rulesets: the classic endpoint 404s when protection is enforced only by a
ruleset, so a classic-only read would emit a false "not configured" finding.

Per the project's design principles, this collector never auto-judges: absence
(404), disabled state, and insufficient-scope (403) responses are captured as
evidence in the ``raw`` payload so a human reviewer can audit exactly what the
API returned. Only an unset token or a genuine auth/transport failure aborts.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv

from evidence import Evidence

API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"
SOURCE = "github"
REQUEST_TIMEOUT = 30


def _now() -> str:
    """Return the current UTC time as an ISO-8601 timestamp."""
    return datetime.now(timezone.utc).isoformat()


def _load_token() -> str:
    """Read the GitHub PAT from the ``GITHUB_PAT`` environment variable.

    Loads ``.env`` via python-dotenv first so local runs pick up the gitignored
    secret without exporting it manually.

    Returns:
        The personal access token string.

    Raises:
        RuntimeError: If ``GITHUB_PAT`` is unset or empty.
    """
    load_dotenv()
    token = os.environ.get("GITHUB_PAT", "").strip()
    if not token:
        raise RuntimeError(
            "GITHUB_PAT is not set. Add it to .env (see .env.example); never "
            "commit or print the token."
        )
    return token


def _github_request(method: str, path: str, *, token: str) -> tuple[int, Any]:
    """Make a single GitHub REST API request.

    Args:
        method: HTTP method, e.g. ``"GET"``.
        path: API path beginning with ``/`` (joined onto :data:`API_BASE`).
        token: The PAT used for ``Authorization: Bearer``.

    Returns:
        A ``(status_code, body)`` tuple. ``body`` is the parsed JSON when the
        response has a JSON body, otherwise ``None`` (e.g. 204 No Content).

    Raises:
        RuntimeError: On HTTP 401 (bad/expired credentials — a config error,
            not a control finding).
        requests.RequestException: On a transport-level failure.

    Non-success statuses other than 401 (e.g. 403, 404, 204) are returned to the
    caller so they can be recorded as evidence rather than aborting collection.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }
    response = requests.request(
        method, f"{API_BASE}{path}", headers=headers, timeout=REQUEST_TIMEOUT
    )
    if response.status_code == 401:
        # Do not echo the response body; it can reflect request details. Never
        # include the token in the message.
        raise RuntimeError(
            "GitHub API returned 401 Unauthorized. The GITHUB_PAT is invalid or "
            "expired; refresh it in .env."
        )

    body: Any = None
    if response.content:
        try:
            body = response.json()
        except ValueError:
            body = None
    return response.status_code, body


def _evidence(
    *,
    evidence_id: str,
    evidence_type: str,
    endpoint: str,
    http_status: int,
    data: Any,
    note: str | None,
) -> Evidence:
    """Build an :class:`Evidence` item with the standard ``raw`` envelope.

    The ``raw`` payload always carries ``endpoint``, ``http_status``, ``data``
    (verbatim API body, possibly ``None``), and a plain-English ``note`` so a
    reviewer can see what the API returned and why the signal reads as it does.
    """
    return Evidence(
        id=evidence_id,
        source=SOURCE,
        type=evidence_type,
        raw={
            "endpoint": endpoint,
            "http_status": http_status,
            "data": data,
            "note": note,
        },
        collected_at=_now(),
    )


def _pull_request_rule(rules: Any) -> dict[str, Any] | None:
    """Return the ``pull_request`` rule from an effective-rules response, if any.

    Args:
        rules: The parsed body of ``GET /repos/{owner}/{repo}/rules/branches/...``
            (a list of rule objects) or ``None``.

    Returns:
        The first rule whose ``type`` is ``"pull_request"``, or ``None``.
    """
    if not isinstance(rules, list):
        return None
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == "pull_request":
            return rule
    return None


def _collect_branch_protection(
    owner: str,
    repo: str,
    branch: str,
    classic_status: int,
    classic_data: Any,
    rules_status: int,
    rules_data: Any,
) -> Evidence:
    """Collect branch protection settings as evidence (github.branch_protection).

    Protection is considered present if EITHER classic branch protection (200)
    OR a non-empty repository ruleset applies to the branch. The ``note`` records
    which mechanism is in force: ``"classic"``, ``"ruleset"``, ``"both"``, or
    ``"none"``.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: Default branch the protection applies to.
        classic_status: HTTP status from the classic protection endpoint.
        classic_data: Parsed body from the classic protection endpoint.
        rules_status: HTTP status from the effective-rules endpoint.
        rules_data: Parsed body (list of rules) from the effective-rules endpoint.

    Returns:
        The branch-protection :class:`Evidence`.
    """
    endpoint = f"/repos/{owner}/{repo}/branches/{branch}/protection (+ /rules/branches/{branch})"
    has_classic = classic_status == 200 and bool(classic_data)
    has_ruleset = rules_status == 200 and isinstance(rules_data, list) and len(rules_data) > 0

    if classic_status == 403 or rules_status == 403:
        note = (
            "PAT lacks repository admin scope to read branch protection; "
            "enforcement state not determinable."
        )
    elif has_classic and has_ruleset:
        note = "branch protection enforced (mechanism: both)"
    elif has_classic:
        note = "branch protection enforced (mechanism: classic)"
    elif has_ruleset:
        note = "branch protection enforced (mechanism: ruleset)"
    else:
        note = "branch protection not configured (mechanism: none)"

    mechanism = (
        "both"
        if (has_classic and has_ruleset)
        else "classic"
        if has_classic
        else "ruleset"
        if has_ruleset
        else "none"
    )
    data = {
        "branch": branch,
        "protection_present": has_classic or has_ruleset,
        "mechanism": mechanism,
        "classic_protection": {"http_status": classic_status, "settings": classic_data},
        "ruleset_rules": {"http_status": rules_status, "rules": rules_data},
    }
    # Surface the most specific status: prefer the mechanism that is in force.
    http_status = classic_status if has_classic else rules_status if has_ruleset else classic_status
    return _evidence(
        evidence_id=f"github.branch_protection.{branch}",
        evidence_type="github.branch_protection",
        endpoint=endpoint,
        http_status=http_status,
        data=data,
        note=note,
    )


def _collect_required_reviews(
    owner: str,
    repo: str,
    branch: str,
    classic_status: int,
    classic_data: Any,
    rules_status: int,
    rules_data: Any,
) -> Evidence:
    """Collect required-review settings as evidence (github.required_reviews).

    Prefers the classic ``required_pull_request_reviews`` block when the classic
    endpoint returned 200; otherwise reads the ``pull_request`` rule from the
    effective-rules response. A required count of 0 is recorded honestly and is
    not treated as absence.

    Args:
        owner: Repository owner.
        repo: Repository name.
        branch: Default branch the reviews apply to.
        classic_status: HTTP status from the classic protection endpoint.
        classic_data: Parsed body from the classic protection endpoint.
        rules_status: HTTP status from the effective-rules endpoint.
        rules_data: Parsed body (list of rules) from the effective-rules endpoint.

    Returns:
        The required-reviews :class:`Evidence`.
    """
    endpoint = f"/repos/{owner}/{repo}/branches/{branch}/protection (+ /rules/branches/{branch})"
    classic_block = (
        classic_data.get("required_pull_request_reviews")
        if classic_status == 200 and isinstance(classic_data, dict)
        else None
    )
    pr_rule = _pull_request_rule(rules_data)

    if classic_block is not None:
        mechanism = "classic"
        params = classic_block
        required_count = params.get("required_approving_review_count")
        details = {
            "required_approving_review_count": required_count,
            "dismiss_stale_reviews": params.get("dismiss_stale_reviews"),
            "require_code_owner_reviews": params.get("require_code_owner_reviews"),
        }
        note = f"required reviews enforced via classic branch protection (count={required_count})"
    elif pr_rule is not None:
        mechanism = "ruleset"
        params = pr_rule.get("parameters", {}) or {}
        required_count = params.get("required_approving_review_count")
        details = {
            "required_approving_review_count": required_count,
            "dismiss_stale_reviews_on_push": params.get("dismiss_stale_reviews_on_push"),
            "require_code_owner_review": params.get("require_code_owner_review"),
        }
        note = f"required reviews enforced via ruleset pull_request rule (count={required_count})"
    elif classic_status == 403 or rules_status == 403:
        mechanism = "unknown"
        details = None
        note = "PAT lacks scope to read review requirements; not determinable."
    else:
        mechanism = "none"
        details = None
        note = "no required reviews (no pull_request rule in classic protection or rulesets)"

    data = {"branch": branch, "mechanism": mechanism, "required_reviews": details}
    http_status = classic_status if classic_block is not None else rules_status
    return _evidence(
        evidence_id=f"github.required_reviews.{branch}",
        evidence_type="github.required_reviews",
        endpoint=endpoint,
        http_status=http_status,
        data=data,
        note=note,
    )


def _collect_two_factor_status(owner: str, *, token: str) -> Evidence:
    """Collect org 2FA enforcement status as evidence (github.two_factor_status).

    Queries ``GET /orgs/{owner}``. For a personal account the endpoint returns
    404; this is recorded as N/A evidence rather than an error, since 2FA
    enforcement is not determinable via the API for a user.

    Args:
        owner: GitHub organization or user login.
        token: The PAT used for the request.

    Returns:
        The two-factor-status :class:`Evidence`.
    """
    endpoint = f"/orgs/{owner}"
    status, body = _github_request("GET", endpoint, token=token)

    if status == 200 and isinstance(body, dict):
        enforced = body.get("two_factor_requirement_enabled")
        data = {"owner": owner, "two_factor_requirement_enabled": enforced}
        if enforced is None:
            note = (
                "org found but two_factor_requirement_enabled not visible; PAT "
                "may lack org admin scope."
            )
        else:
            note = f"organization 2FA enforcement enabled={enforced}"
    elif status == 404:
        data = {"owner": owner, "two_factor_requirement_enabled": None}
        note = (
            "owner is not an organization — 2FA enforcement not determinable via "
            "API for a personal account."
        )
    elif status == 403:
        data = {"owner": owner, "two_factor_requirement_enabled": None}
        note = "PAT lacks org admin scope; 2FA enforcement not determinable."
    else:
        data = {"owner": owner, "two_factor_requirement_enabled": None}
        note = f"unexpected status {status} reading org 2FA enforcement."

    return _evidence(
        evidence_id=f"github.two_factor_status.{owner}",
        evidence_type="github.two_factor_status",
        endpoint=endpoint,
        http_status=status,
        data=data,
        note=note,
    )


def _collect_dependabot_status(owner: str, repo: str, *, token: str) -> Evidence:
    """Collect Dependabot enablement as evidence (github.dependabot_status).

    Queries ``GET /repos/{owner}/{repo}/vulnerability-alerts`` where 204 means
    enabled and 404 means disabled.

    Args:
        owner: Repository owner.
        repo: Repository name.
        token: The PAT used for the request.

    Returns:
        The dependabot-status :class:`Evidence`.
    """
    endpoint = f"/repos/{owner}/{repo}/vulnerability-alerts"
    status, _ = _github_request("GET", endpoint, token=token)

    if status == 204:
        enabled: bool | None = True
        note = "Dependabot vulnerability alerts enabled."
    elif status == 404:
        enabled = False
        note = "Dependabot vulnerability alerts disabled."
    elif status == 403:
        enabled = None
        note = "PAT lacks scope to read Dependabot alert status; not determinable."
    else:
        enabled = None
        note = f"unexpected status {status} reading Dependabot alert status."

    return _evidence(
        evidence_id=f"github.dependabot_status.{repo}",
        evidence_type="github.dependabot_status",
        endpoint=endpoint,
        http_status=status,
        data={"repo": repo, "enabled": enabled},
        note=note,
    )


def _collect_dependabot_alerts(owner: str, repo: str, *, token: str) -> Evidence:
    """Collect open Dependabot alerts as evidence (github.dependabot_alerts).

    Queries ``GET /repos/{owner}/{repo}/dependabot/alerts?state=open``. The raw
    payload records the open count and a trimmed per-alert summary.

    Args:
        owner: Repository owner.
        repo: Repository name.
        token: The PAT used for the request.

    Returns:
        The dependabot-alerts :class:`Evidence`.
    """
    endpoint = f"/repos/{owner}/{repo}/dependabot/alerts?state=open&per_page=100"
    status, body = _github_request("GET", endpoint, token=token)

    if status == 200 and isinstance(body, list):
        summary = [
            {
                "number": a.get("number"),
                "severity": (a.get("security_advisory") or {}).get("severity"),
                "package": (
                    ((a.get("dependency") or {}).get("package") or {}).get("name")
                ),
                "state": a.get("state"),
            }
            for a in body
            if isinstance(a, dict)
        ]
        data: dict[str, Any] = {"repo": repo, "open_count": len(summary), "alerts": summary}
        note = f"{len(summary)} open Dependabot alert(s)."
    elif status == 403:
        data = {"repo": repo, "open_count": None, "alerts": None}
        note = (
            "Dependabot alerts unavailable: feature disabled or PAT lacks "
            "security-events scope."
        )
    elif status == 404:
        data = {"repo": repo, "open_count": None, "alerts": None}
        note = "Dependabot alerts not enabled for this repository."
    else:
        data = {"repo": repo, "open_count": None, "alerts": None}
        note = f"unexpected status {status} reading Dependabot alerts."

    return _evidence(
        evidence_id=f"github.dependabot_alerts.{repo}",
        evidence_type="github.dependabot_alerts",
        endpoint=endpoint,
        http_status=status,
        data=data,
        note=note,
    )


def _collect_secret_scanning(
    owner: str, repo: str, repo_status: int, repo_data: Any
) -> Evidence:
    """Collect secret-scanning status as evidence (github.secret_scanning).

    Reads ``security_and_analysis.secret_scanning.status`` from the already
    fetched repository payload (``enabled``/``disabled``/absent).

    Args:
        owner: Repository owner.
        repo: Repository name.
        repo_status: HTTP status from the repository endpoint.
        repo_data: Parsed body from ``GET /repos/{owner}/{repo}``.

    Returns:
        The secret-scanning :class:`Evidence`.
    """
    endpoint = f"/repos/{owner}/{repo}"
    sec = (
        (repo_data.get("security_and_analysis") or {})
        if repo_status == 200 and isinstance(repo_data, dict)
        else {}
    )
    scanning = (sec.get("secret_scanning") or {}) if isinstance(sec, dict) else {}
    status_value = scanning.get("status") if isinstance(scanning, dict) else None

    if status_value == "enabled":
        note = "secret scanning enabled."
    elif status_value == "disabled":
        note = "secret scanning disabled."
    elif repo_status == 200:
        note = (
            "secret scanning status not reported (often unavailable on private "
            "repos without GitHub Advanced Security, or PAT lacks admin scope)."
        )
    else:
        note = f"repository payload unavailable (status {repo_status}); status not determinable."

    return _evidence(
        evidence_id=f"github.secret_scanning.{repo}",
        evidence_type="github.secret_scanning",
        endpoint=endpoint,
        http_status=repo_status,
        data={"repo": repo, "status": status_value},
        note=note,
    )


def collect_github_evidence(owner: str, repo: str) -> list[Evidence]:
    """Collect all v1 GitHub evidence for a repository.

    Fetches the shared payloads (repository metadata, classic branch protection,
    and effective branch rules) once each, then normalizes the six v1 signals
    into the shared :class:`Evidence` schema.

    Args:
        owner: GitHub organization or user that owns the repository.
        repo: Repository name.

    Returns:
        A list of :class:`Evidence` items, one per collected signal, in a stable
        order: branch_protection, required_reviews, two_factor_status,
        dependabot_status, dependabot_alerts, secret_scanning.

    Raises:
        RuntimeError: If ``GITHUB_PAT`` is unset, or the API returns 401.
        requests.RequestException: On a transport-level failure.
    """
    token = _load_token()

    repo_status, repo_data = _github_request("GET", f"/repos/{owner}/{repo}", token=token)
    branch = (
        repo_data.get("default_branch", "main")
        if repo_status == 200 and isinstance(repo_data, dict)
        else "main"
    )

    classic_status, classic_data = _github_request(
        "GET", f"/repos/{owner}/{repo}/branches/{branch}/protection", token=token
    )
    rules_status, rules_data = _github_request(
        "GET", f"/repos/{owner}/{repo}/rules/branches/{branch}", token=token
    )

    return [
        _collect_branch_protection(
            owner, repo, branch, classic_status, classic_data, rules_status, rules_data
        ),
        _collect_required_reviews(
            owner, repo, branch, classic_status, classic_data, rules_status, rules_data
        ),
        _collect_two_factor_status(owner, token=token),
        _collect_dependabot_status(owner, repo, token=token),
        _collect_dependabot_alerts(owner, repo, token=token),
        _collect_secret_scanning(owner, repo, repo_status, repo_data),
    ]

"""Human approval queue for proposed evidence-to-control mappings.

Mappings proposed by :mod:`agent.mapper` never auto-accept. Each lands in the
queue as ``pending`` and is written to two artifacts:

    - ``review_queue.json`` — machine-readable queue state.
    - ``REVIEW.md`` — human-readable summary for the reviewer.

A mapping only becomes ``approved`` when a human explicitly approves it via
:func:`approve`. This module is the enforcement point for the "nothing
auto-accepts" design principle.

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

from typing import Any

QUEUE_PATH = "review_queue.json"
REVIEW_MD_PATH = "REVIEW.md"


def enqueue_pending(mappings: list[Any]) -> None:
    """Add proposed mappings to the queue as ``pending`` and rewrite artifacts.

    Args:
        mappings: Proposed mappings (see :class:`agent.mapper.Mapping`) to queue
            for human review. Each is recorded with status ``pending``.

    Raises:
        NotImplementedError: Always, until the queue is implemented.
    """
    raise NotImplementedError


def load_queue() -> list[dict[str, Any]]:
    """Load the current review queue from ``review_queue.json``.

    Returns:
        The queue entries, each a dict including its ``status``.

    Raises:
        NotImplementedError: Always, until the queue is implemented.
    """
    raise NotImplementedError


def approve(control_id: str, reviewer: str) -> None:
    """Mark a pending mapping as approved by a human reviewer.

    Args:
        control_id: The control whose pending mapping is being approved.
        reviewer: Identifier of the human approving the mapping.

    Raises:
        NotImplementedError: Always, until the queue is implemented.
    """
    raise NotImplementedError

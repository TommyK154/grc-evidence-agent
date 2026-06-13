"""Evaluation harness: score agent mappings against the golden set.

Compares the agent's proposed mappings to the hand-labeled ground truth in
``evals/golden.yaml`` and reports precision/recall per control. Results are both
printed and written to ``evals/results.md``.

This module is strictly read-only with respect to ``evals/golden.yaml`` — the
golden set is human-authored and must never be written by code.

No implementation yet; this is a scaffold stub.
"""

from __future__ import annotations

from typing import Any

GOLDEN_PATH = "evals/golden.yaml"
RESULTS_PATH = "evals/results.md"


def load_golden() -> dict[str, Any]:
    """Load the hand-labeled ground truth (read-only).

    Returns:
        The parsed golden set keyed by control id.

    Raises:
        NotImplementedError: Always, until the harness is implemented.
    """
    raise NotImplementedError


def score(
    predicted: list[Any],
    golden: dict[str, Any],
) -> dict[str, dict[str, float]]:
    """Compute precision/recall per control.

    Args:
        predicted: Mappings proposed by the agent (see
            :class:`agent.mapper.Mapping`).
        golden: Ground-truth mappings from :func:`load_golden`.

    Returns:
        A dict keyed by control id, each value holding at least ``precision``
        and ``recall``.

    Raises:
        NotImplementedError: Always, until the harness is implemented.
    """
    raise NotImplementedError


def main() -> None:
    """Run the evaluation end to end: load, score, print, and write results.

    Raises:
        NotImplementedError: Always, until the harness is implemented.
    """
    raise NotImplementedError


if __name__ == "__main__":
    main()

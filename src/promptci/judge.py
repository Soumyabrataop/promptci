"""LLM-as-judge scoring. The judge is just another model call with a strict JSON contract."""

from __future__ import annotations

import json
import re

from .errors import JudgeError
from .providers import BaseProvider, MockProvider

JUDGE_SYSTEM = (
    "You are a strict, impartial evaluator. Score the RESPONSE against the RUBRIC "
    "on a scale from 0.0 to 1.0. Be conservative: 1.0 means the response fully "
    "satisfies the rubric. Reply with ONLY a JSON object of the form "
    '{"score": 0.0, "reason": "one short sentence"}.'
)


def judge_output(
    provider: BaseProvider, model: str, rubric: str, output: str
) -> tuple[float, str]:
    """Return (score in [0,1], reason)."""
    if isinstance(provider, MockProvider):
        # The mock has no understanding of text; judges auto-pass offline so demo
        # workflows and tests can exercise the full pipeline deterministically.
        return 1.0, "mock provider — judge auto-passes"

    user = (
        f"RUBRIC:\n{rubric}\n\nRESPONSE:\n{output}\n\n"
        "Reply with only the JSON object, no other text."
    )
    raw = provider.complete(model=model, system=JUDGE_SYSTEM, user=user, temperature=0.0, timeout=60.0)

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise JudgeError(f"judge did not return a JSON object: {raw[:200]!r}")
    try:
        data = json.loads(match.group(0))
        score = float(data["score"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        raise JudgeError(f"judge returned an unusable score: {raw[:200]!r} ({e})") from e
    score = min(1.0, max(0.0, score))
    reason = str(data.get("reason", ""))
    return score, reason

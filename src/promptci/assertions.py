"""Quality gates: deterministic checks (free, instant) + LLM-judge checks (semantic)."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .errors import ConfigError, JudgeError, PromptCIError, ProviderError
from .schema import CheckSpec

# judge_fn(rubric, output) -> (score, reason)
JudgeFn = Callable[[str, str], "tuple[float, str]"]

_JSON_TYPES: dict[str, Any] = {
    "string": str,
    "number": (int, float),
    "integer": int,
    "boolean": bool,
    "array": list,
    "object": dict,
    "null": type(None),
}


@dataclass
class AssertionResult:
    type: str
    passed: bool
    detail: str
    score: float | None = None


def evaluate_checks(checks: list[CheckSpec], output: str, judge_fn: JudgeFn) -> list[AssertionResult]:
    results: list[AssertionResult] = []
    for check in checks:
        result = _evaluate_one(check, output, judge_fn)
        results.append(result)
    return results


def _evaluate_one(check: CheckSpec, output: str, judge_fn: JudgeFn) -> AssertionResult:
    try:
        if check.type == "contains":
            values = _as_list(check.value, check.type)
            missing = [v for v in values if v not in output]
            passed, detail = not missing, (
                "all substrings present" if not missing else f"missing: {missing!r}"
            )
        elif check.type == "not_contains":
            values = _as_list(check.value, check.type)
            present = [v for v in values if v in output]
            passed, detail = not present, (
                "none present" if not present else f"found forbidden: {present!r}"
            )
        elif check.type == "regex":
            if not check.pattern:
                raise ConfigError("regex check requires 'pattern'")
            matched = re.search(check.pattern, output, re.DOTALL)
            passed, detail = bool(matched), (
                "pattern matched" if matched else f"pattern {check.pattern!r} not found"
            )
        elif check.type == "min_length":
            n, need = len(output), int(check.value)
            passed, detail = n >= need, f"length {n} >= {need}"
        elif check.type == "max_length":
            n, cap = len(output), int(check.value)
            passed, detail = n <= cap, f"length {n} <= {cap}"
        elif check.type == "json_schema":
            passed, detail = _check_json_schema(output, check.json_schema or {})
        elif check.type == "llm_judge":
            if not check.rubric:
                raise ConfigError("llm_judge check requires 'rubric'")
            score, reason = judge_fn(check.rubric, output)
            passed = score >= check.threshold
            detail = (
                f"score {score:.2f} >= {check.threshold:.2f}: {reason}"
                if passed
                else f"score {score:.2f} < {check.threshold:.2f}: {reason}"
            )
            return AssertionResult(type=check.type, passed=passed, detail=detail, score=score)
        else:  # pragma: no cover - schema Literal rejects unknown types earlier
            passed, detail = False, f"unsupported check type '{check.type}'"
    except (ConfigError, JudgeError, ProviderError) as e:
        passed, detail = False, str(e)
    return AssertionResult(type=check.type, passed=passed, detail=detail)


def _as_list(value: Any, check_type: str) -> list[str]:
    if value is None:
        raise ConfigError(f"{check_type} check requires 'value' (string or list of strings)")
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    raise ConfigError(f"{check_type} check 'value' must be a string or list of strings")


def _check_json_schema(output: str, schema: dict[str, Any]) -> tuple[bool, str]:
    """Shallow structural validation: valid JSON + required keys + declared types at top level."""
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        return False, f"output is not valid JSON ({e})"
    problems: list[str] = []
    if schema.get("type") == "object" and not isinstance(data, dict):
        problems.append("expected a JSON object")
    for key in schema.get("required", []):
        if not (isinstance(data, dict) and key in data):
            problems.append(f"missing key '{key}'")
    for key, spec in (schema.get("properties") or {}).items():
        if not (isinstance(data, dict) and key in data):
            continue
        want = _JSON_TYPES.get(spec.get("type", ""))
        got = data[key]
        if want and not isinstance(got, want) or (
            spec.get("type") in ("number", "integer") and isinstance(got, bool)
        ):
            problems.append(f"'{key}' should be {spec['type']}, got {type(got).__name__}")
    return (not problems), ("valid" if not problems else "; ".join(problems))


__all__ = ["AssertionResult", "PromptCIError", "evaluate_checks"]

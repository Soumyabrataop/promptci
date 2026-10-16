from __future__ import annotations

import json

from promptci.assertions import evaluate_checks
from promptci.schema import CheckSpec


def judge_yes(rubric, output):
    return 0.95, "fine"


def judge_no(rubric, output):
    return 0.2, "nope"


def test_contains_and_not_contains():
    checks = [
        CheckSpec(type="contains", value=["hello", "world"]),
        CheckSpec(type="not_contains", value="TODO"),
    ]
    results = evaluate_checks(checks, "hello world, clean", judge_yes)
    assert all(r.passed for r in results)

    results = evaluate_checks(checks, "hello there TODO", judge_yes)
    assert results[0].passed is False and "missing" in results[0].detail
    assert results[1].passed is False and "TODO" in results[1].detail


def test_regex():
    results = evaluate_checks([CheckSpec(type="regex", pattern=r"(?i)ready to send")], "Ready to send.", judge_yes)
    assert results[0].passed


def test_lengths():
    checks = [CheckSpec(type="min_length", value=3), CheckSpec(type="max_length", value=10)]
    results = evaluate_checks(checks, "hello", judge_yes)
    assert all(r.passed for r in results)
    assert evaluate_checks([CheckSpec(type="max_length", value=2)], "hello", judge_yes)[0].passed is False


def test_json_schema():
    output = json.dumps({"title": "T", "poem": "P"})
    schema = {
        "type": "object",
        "required": ["title", "poem"],
        "properties": {"title": {"type": "string"}, "poem": {"type": "string"}},
    }
    results = evaluate_checks([CheckSpec(type="json_schema", schema=schema)], output, judge_yes)
    assert results[0].passed

    bad = evaluate_checks([CheckSpec(type="json_schema", schema=schema)], "not json", judge_yes)
    assert bad[0].passed is False and "not valid JSON" in bad[0].detail

    missing = evaluate_checks([CheckSpec(type="json_schema", schema=schema)], '{"title": "T"}', judge_yes)
    assert missing[0].passed is False and "poem" in missing[0].detail

    wrong_type = evaluate_checks(
        [CheckSpec(type="json_schema", schema=schema)], '{"title": 1, "poem": "P"}', judge_yes
    )
    assert wrong_type[0].passed is False and "string" in wrong_type[0].detail


def test_llm_judge_threshold():
    check = CheckSpec(type="llm_judge", rubric="be nice", threshold=0.7)
    assert evaluate_checks([check], "x", judge_yes)[0].passed
    assert evaluate_checks([check], "x", judge_no)[0].passed is False


def test_judge_missing_rubric_is_failure_not_crash():
    check = CheckSpec(type="llm_judge", threshold=0.7)
    result = evaluate_checks([check], "x", judge_yes)[0]
    assert result.passed is False and "rubric" in result.detail

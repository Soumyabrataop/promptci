"""End-to-end runs against the mock provider — no network, no model server."""

from __future__ import annotations

import json

from promptci.loader import load_workflow
from promptci.report import write_reports
from promptci.runner import run_workflow
from tests.util import build_project

WORKFLOW = {
    "name": "e2e",
    "defaults": {"base_url": "mock://", "model": "mock"},
    "inputs": {"product": "PromptCI"},
    "steps": [
        {
            "id": "draft",
            "prompt": "prompts/draft.md",
            "checks": [
                {"type": "not_contains", "value": ["TODO"]},
                {"type": "max_length", "value": 5000},
            ],
        },
        {
            "id": "review",
            "prompt": "prompts/review.md",
            "inputs": {"draft": "${{ steps.draft.output }}"},
            "checks": [
                {"type": "regex", "pattern": "(?i)ready to send"},
                {"type": "llm_judge", "rubric": "confirms ready", "threshold": 0.5},
            ],
        },
    ],
}

PROMPTS = {
    "prompts/draft.md": "Write an email about {{ product }}.\nMOCK_RESPONSE: Welcome to {{ product }}! Enjoy.",
    "prompts/review.md": "Review:\n{{ draft }}\nMOCK_RESPONSE: Looks good — ready to send.",
}


def _load(tmp_path):
    build_project(tmp_path, WORKFLOW, PROMPTS)
    return load_workflow(tmp_path / "promptci.yaml")


def test_run_passes_and_records_snapshots(tmp_path):
    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir)
    assert result.ok
    assert [o.status for o in result.outcomes] == ["pass", "pass"]
    assert result.snapshots_path is not None and result.snapshots_path.is_file()

    # second run is stable
    again = run_workflow(wf, project_dir)
    assert again.ok and all(o.drift == "same" for o in again.outcomes)


def test_frozen_fails_after_prompt_change(tmp_path):
    wf, project_dir = _load(tmp_path)
    assert run_workflow(wf, project_dir).ok

    (project_dir / "prompts" / "draft.md").write_text(
        "Write an email about {{ product }}.\nMOCK_RESPONSE: Brand new response text.",
        encoding="utf-8",
    )
    result = run_workflow(wf, project_dir, frozen=True)
    assert not result.ok
    draft = next(o for o in result.outcomes if o.id == "draft")
    assert draft.status == "fail" and draft.drift == "signature_drift"


def test_plain_run_rebaselines_after_change(tmp_path):
    wf, project_dir = _load(tmp_path)
    run_workflow(wf, project_dir)
    (project_dir / "prompts" / "draft.md").write_text(
        "Write an email about {{ product }}.\nMOCK_RESPONSE: Brand new response text.",
        encoding="utf-8",
    )
    result = run_workflow(wf, project_dir)  # not frozen: records new baseline
    assert result.ok
    assert run_workflow(wf, project_dir, frozen=True).ok


def test_failing_check_fails_run(tmp_path):
    wf, project_dir = _load(tmp_path)
    wf.steps[0].checks[0].type = "contains"  # the draft cannot contain this
    wf.steps[0].checks[0].value = ["XYZZY-must-not-appear"]
    result = run_workflow(wf, project_dir)
    assert not result.ok
    draft = next(o for o in result.outcomes if o.id == "draft")
    assert draft.status == "fail"
    assert draft.checks[0].passed is False
    # review still ran (no fail-fast) and passed
    review = next(o for o in result.outcomes if o.id == "review")
    assert review.status == "pass"


def test_fail_fast_stops_after_first_failure(tmp_path):
    wf, project_dir = _load(tmp_path)
    wf.steps[0].checks[0].type = "contains"
    wf.steps[0].checks[0].value = ["XYZZY"]
    result = run_workflow(wf, project_dir, fail_fast=True)
    assert [o.status for o in result.outcomes] == ["fail"]


def test_only_step_skips_others(tmp_path):
    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir, only_step="draft")
    assert [o.status for o in result.outcomes] == ["pass", "skipped"]
    assert result.ok


def test_var_override_reaches_template(tmp_path):
    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir, var_overrides={"product": "Acme"})
    draft = next(o for o in result.outcomes if o.id == "draft")
    assert "Acme" in draft.rendered_prompt


def test_step_output_feeds_next_prompt(tmp_path):
    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir)
    review = next(o for o in result.outcomes if o.id == "review")
    assert "Welcome to PromptCI! Enjoy." in review.rendered_prompt


def test_reports_written(tmp_path):
    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir)
    md_path, json_path = write_reports(result, project_dir)
    assert md_path.is_file() and json_path.is_file()
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["ok"] is True and len(data["steps"]) == 2
    assert "# PromptCI run — e2e" in md_path.read_text(encoding="utf-8")


def test_provider_error_is_step_error_not_crash(tmp_path):
    from promptci.errors import ProviderError
    from promptci.providers import BaseProvider

    class BoomProvider(BaseProvider):
        name = "boom"

        def complete(self, **kwargs):
            raise ProviderError("simulated outage")

    wf, project_dir = _load(tmp_path)
    result = run_workflow(wf, project_dir, provider=BoomProvider())
    assert not result.ok
    assert all(o.status == "error" for o in result.outcomes)
    assert "simulated outage" in result.outcomes[0].error

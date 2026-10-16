from __future__ import annotations

import pytest

from promptci.errors import ConfigError
from promptci.loader import load_workflow, validate_structure

VALID = """
name: demo
inputs:
  product: PromptCI
steps:
  - id: draft
    prompt: prompts/draft.md
    checks:
      - type: contains
        value: hello
  - id: review
    prompt: prompts/review.md
    inputs:
      draft: ${{ steps.draft.output }}
"""


def test_load_valid(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "draft.md").write_text("x")
    (tmp_path / "prompts" / "review.md").write_text("x")
    wf, project_dir = load_workflow(_write(tmp_path, VALID))
    assert wf.name == "demo"
    assert len(wf.steps) == 2
    assert project_dir == tmp_path.resolve()


def test_assert_alias_accepted(tmp_path):
    wf, _ = load_workflow(_write(tmp_path, VALID.replace("checks:", "assert:")))
    assert wf.steps[0].checks[0].type == "contains"


def test_duplicate_step_ids_rejected(tmp_path):
    bad = VALID + "  - id: draft\n    prompt: prompts/draft.md\n"
    with pytest.raises(ConfigError, match="duplicate step id"):
        load_workflow(_write(tmp_path, bad))


def test_unknown_check_type_rejected(tmp_path):
    bad = VALID.replace("type: contains", "type: telepathy")
    with pytest.raises(ConfigError, match="telepathy"):
        load_workflow(_write(tmp_path, bad))


def test_invalid_yaml(tmp_path):
    (tmp_path / "promptci.yaml").write_text("steps: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_workflow(tmp_path / "promptci.yaml")


def test_missing_prompt_file_is_error(tmp_path):
    wf, project_dir = load_workflow(_write(tmp_path, VALID))
    errors, _ = validate_structure(wf, project_dir)
    assert any("prompt file not found" in e for e in errors)


def test_forward_reference_is_error(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "draft.md").write_text("x")
    (tmp_path / "prompts" / "review.md").write_text("x")
    bad = """
name: demo
steps:
  - id: first
    prompt: prompts/draft.md
    inputs:
      draft: ${{ steps.second.output }}
  - id: second
    prompt: prompts/review.md
"""
    wf, project_dir = load_workflow(_write(tmp_path, bad))
    errors, _ = validate_structure(wf, project_dir)
    assert any("forward reference" in e for e in errors)


def test_unknown_input_is_warning(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "draft.md").write_text("x")
    wf, project_dir = load_workflow(_write(tmp_path, VALID))
    wf.steps[0].inputs = {"mystery": "${{ inputs.mystery }}"}
    _, warnings = validate_structure(wf, project_dir)
    assert any("--var" in w for w in warnings)


def _write(tmp_path, text: str):
    p = tmp_path / "promptci.yaml"
    p.write_text(text, encoding="utf-8")
    return p

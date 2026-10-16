from __future__ import annotations

import pytest

from promptci.errors import ConfigError
from promptci.templating import RunContext, interpolate, make_env, render_prompt


def test_whole_string_ref_preserves_type():
    ctx = RunContext(inputs={"n": 42})
    assert interpolate("${{ inputs.n }}", ctx) == 42


def test_spliced_ref_is_stringified():
    ctx = RunContext(inputs={"n": 42})
    assert interpolate("value=${{ inputs.n }}!", ctx) == "value=42!"


def test_steps_output_ref():
    ctx = RunContext(inputs={}, steps={"draft": "hello world"})
    assert interpolate("${{ steps.draft.output }}", ctx) == "hello world"


def test_steps_json_ref():
    ctx = RunContext(inputs={}, steps={"draft": '{"title": "T", "poem": "P"}'})
    assert interpolate("${{ steps.draft.json.poem }}", ctx) == "P"


def test_env_ref_missing_is_empty():
    ctx = RunContext(inputs={})
    assert interpolate("${{ env.DEFINITELY_NOT_SET_XYZ }}", ctx) == ""


def test_unknown_input_raises():
    with pytest.raises(ConfigError, match="unknown input"):
        interpolate("${{ inputs.nope }}", RunContext(inputs={}))


def test_forward_reference_raises():
    with pytest.raises(ConfigError, match="forward-referenced"):
        interpolate("${{ steps.later.output }}", RunContext(inputs={}))


def test_unsupported_root_raises():
    with pytest.raises(ConfigError, match="unsupported reference"):
        interpolate("${{ secrets.API_KEY }}", RunContext(inputs={}))


def test_render_strict_undefined(tmp_path):
    (tmp_path / "p.md").write_text("Hello {{ name }}!", encoding="utf-8")
    env = make_env(tmp_path)
    with pytest.raises(ConfigError, match="name"):
        render_prompt(env, "p.md", {})
    assert render_prompt(env, "p.md", {"name": "Ada"}) == "Hello Ada!"


def test_render_include_between_prompts(tmp_path):
    (tmp_path / "a.md").write_text("A {% include 'b.md' %}", encoding="utf-8")
    (tmp_path / "b.md").write_text("B", encoding="utf-8")
    env = make_env(tmp_path)
    assert render_prompt(env, "a.md", {}) == "A B"

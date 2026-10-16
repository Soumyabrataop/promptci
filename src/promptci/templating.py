"""Prompt rendering (jinja2) and ${{ ... }} input interpolation."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import jinja2

from .errors import ConfigError
from .loader import REF_RE


class RunContext:
    """Everything a step's inputs may reference: workflow inputs + outputs of earlier steps."""

    def __init__(self, inputs: dict[str, Any], steps: dict[str, str] | None = None):
        self.inputs = inputs
        self.steps: dict[str, str] = dict(steps or {})


def make_env(project_dir: Path) -> jinja2.Environment:
    # Templates load relative to the project dir so prompts can {% include %} each other.
    return jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(project_dir)),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        autoescape=False,
    )


def render_prompt(env: jinja2.Environment, template_rel: str, variables: dict[str, Any]) -> str:
    try:
        template = env.get_template(template_rel.replace("\\", "/"))
        return template.render(**variables)
    except jinja2.TemplateError as e:
        raise ConfigError(f"template '{template_rel}' failed to render: {e}") from e


def interpolate(value: Any, ctx: RunContext) -> Any:
    """Resolve ${{ ... }} references in a step's inputs.

    A string that is exactly one reference keeps the resolved value's type;
    otherwise resolved values are stringified and spliced into the text.
    """
    if isinstance(value, dict):
        return {k: interpolate(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [interpolate(v, ctx) for v in value]
    if not isinstance(value, str):
        return value

    matches = list(REF_RE.finditer(value))
    if not matches:
        return value
    if len(matches) == 1 and matches[0].span() == (0, len(value)):
        return _resolve_ref(matches[0].group(1).strip(), ctx)

    def repl(m: re.Match[str]) -> str:
        resolved = _resolve_ref(m.group(1).strip(), ctx)
        return resolved if isinstance(resolved, str) else json.dumps(resolved)

    return REF_RE.sub(repl, value)


def _resolve_ref(ref: str, ctx: RunContext) -> Any:
    parts = [p.strip() for p in ref.split(".")]
    root = parts[0]

    if root == "inputs":
        if len(parts) < 2:
            raise ConfigError(f"'{ref}': expected inputs.<name>")
        node: Any = ctx.inputs
        for p in parts[1:]:
            if isinstance(node, dict) and p in node:
                node = node[p]
            else:
                known = ", ".join(sorted(ctx.inputs)) or "none"
                raise ConfigError(f"'{ref}': unknown input (known inputs: {known})")
        return node

    if root == "steps":
        if len(parts) < 2:
            raise ConfigError(f"'{ref}': expected steps.<id>.output")
        sid = parts[1]
        if sid not in ctx.steps:
            raise ConfigError(
                f"'{ref}': unknown or forward-referenced step '{sid}' "
                "(steps can only use outputs of earlier steps)"
            )
        output = ctx.steps[sid]
        if len(parts) == 2 or parts[2] == "output":
            if len(parts) > 3:
                raise ConfigError(f"'{ref}': too deep")
            return output
        if parts[2] == "json":
            try:
                data = json.loads(output)
            except json.JSONDecodeError as e:
                raise ConfigError(f"'{ref}': step output is not valid JSON ({e})") from e
            node = data
            for p in parts[3:]:
                if isinstance(node, dict) and p in node:
                    node = node[p]
                else:
                    raise ConfigError(f"'{ref}': path not found in step output")
            return node
        raise ConfigError(
            f"'{ref}': supported forms are steps.<id>.output and steps.<id>.json.<path>"
        )

    if root == "env":
        if len(parts) != 2:
            raise ConfigError(f"'{ref}': expected env.<NAME>")
        return os.environ.get(parts[1], "")

    raise ConfigError(f"unsupported reference '{ref}' (use inputs.*, steps.*, env.*)")

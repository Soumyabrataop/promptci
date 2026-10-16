"""Find, load, and structurally validate workflow files."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .errors import ConfigError
from .schema import Workflow

DEFAULT_WORKFLOW_NAMES = ("promptci.yaml", "promptci.yml", ".promptci/workflow.yaml")

# ${{ steps.draft.output }} — one regex shared with the interpolator
REF_RE = re.compile(r"\$\{\{\s*(.+?)\s*\}\}")


def find_workflow_file(explicit: str | Path | None) -> Path:
    if explicit is not None:
        p = Path(explicit)
        if not p.is_file():
            raise ConfigError(f"workflow file not found: {p}")
        return p
    for name in DEFAULT_WORKFLOW_NAMES:
        p = Path(name)
        if p.is_file():
            return p
    raise ConfigError(
        "no workflow file found — expected promptci.yaml in this directory "
        "(or pass a path), or run `promptci init`"
    )


def load_workflow(path: str | Path) -> tuple[Workflow, Path]:
    """Load and validate a workflow file. Returns (workflow, project_dir)."""
    p = Path(path)
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except OSError as e:
        raise ConfigError(f"could not read {p}: {e}") from e
    except yaml.YAMLError as e:
        raise ConfigError(f"invalid YAML in {p}: {e}") from e
    if not isinstance(raw, dict):
        raise ConfigError(f"{p} must contain a YAML mapping at the top level")
    try:
        wf = Workflow.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"invalid workflow in {p}:\n{_format_validation_error(e)}") from e
    return wf, p.parent.resolve()


def _format_validation_error(e: ValidationError) -> str:
    lines = []
    for err in e.errors():
        loc = ".".join(str(part) for part in err["loc"]) or "<root>"
        got = repr(err.get("input"))
        if len(got) > 60:
            got = got[:57] + "..."
        lines.append(f"  - {loc}: {err['msg']} (got {got})")
    return "\n".join(lines)


def validate_structure(wf: Workflow, project_dir: Path) -> tuple[list[str], list[str]]:
    """Static checks that don't need a model server. Returns (errors, warnings)."""
    errors: list[str] = []
    warnings: list[str] = []
    ids = [s.id for s in wf.steps]

    for i, step in enumerate(wf.steps):
        if not (project_dir / step.prompt).is_file():
            errors.append(f"step '{step.id}': prompt file not found: {step.prompt}")
        for ref in _refs_in(step.inputs):
            parts = [p.strip() for p in ref.split(".")]
            root = parts[0]
            if root == "steps":
                if len(parts) < 2:
                    errors.append(f"step '{step.id}': malformed reference '{ref}'")
                elif parts[1] not in ids:
                    errors.append(f"step '{step.id}': reference '{ref}' points at unknown step")
                elif ids.index(parts[1]) >= i:
                    errors.append(
                        f"step '{step.id}': reference '{ref}' is a forward reference — "
                        "steps can only use outputs of earlier steps"
                    )
            elif root == "inputs":
                name = parts[1] if len(parts) > 1 else ""
                if not name:
                    errors.append(f"step '{step.id}': malformed reference '{ref}'")
                elif name not in wf.inputs:
                    warnings.append(
                        f"step '{step.id}': input '{name}' is not defined in workflow inputs "
                        "(it must be supplied with --var)"
                    )
            elif root == "env":
                if len(parts) != 2:
                    errors.append(f"step '{step.id}': malformed reference '{ref}'")
            else:
                errors.append(
                    f"step '{step.id}': unsupported reference '{ref}' (use inputs.*, steps.*, env.*)"
                )
    return errors, warnings


def _refs_in(value: Any) -> list[str]:
    """Collect every ${{ ... }} reference appearing anywhere in a value."""
    if isinstance(value, dict):
        return [r for v in value.values() for r in _refs_in(v)]
    if isinstance(value, list):
        return [r for v in value for r in _refs_in(v)]
    if isinstance(value, str):
        return [m.group(1).strip() for m in REF_RE.finditer(value)]
    return []

"""Shared test helpers."""

from __future__ import annotations

from pathlib import Path

import yaml


def build_project(tmp_path: Path, workflow: dict, prompts: dict[str, str]) -> Path:
    """Write a runnable PromptCI project into tmp_path and return the project dir."""
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "promptci.yaml").write_text(yaml.safe_dump(workflow), encoding="utf-8")
    for rel, content in prompts.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return tmp_path

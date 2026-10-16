"""Snapshot baselines for regression testing.

Each step records a snapshot: a signature (hash of rendered prompt + model + resolved
inputs) and the output that was produced. On later runs:

- signature unchanged + output unchanged -> "same"
- signature unchanged + output changed   -> "output_drift" (model misbehaving)
- signature changed (you edited the prompt/inputs/model) -> "signature_drift"

A plain `promptci run` records new snapshots as you go. `promptci run --frozen`
fails on any drift — that is the mode CI should use, so a prompt change that
shifts outputs fails the build until you re-baseline with a plain run.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

Drift = str  # "same" | "new" | "output_drift" | "signature_drift"


def snapshots_file(project_dir: Path, workflow_name: str) -> Path:
    slug = _slug(workflow_name)
    return Path(project_dir) / ".promptci" / "snapshots" / f"{slug}.json"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "workflow"


def signature_of(rendered_prompt: str, model: str, inputs: dict[str, Any]) -> str:
    payload = json.dumps(
        {"prompt": rendered_prompt, "model": model, "inputs": inputs},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SnapshotStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = {}
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    def compare(self, step_id: str, signature: str, output: str) -> Drift:
        entry = self.data.get(step_id)
        if not entry:
            return "new"
        if entry.get("signature") != signature:
            return "signature_drift"
        if str(entry.get("output", "")).strip() != output.strip():
            return "output_drift"
        return "same"

    def record(self, step_id: str, signature: str, model: str, output: str) -> None:
        self.data[step_id] = {
            "signature": signature,
            "model": model,
            "output": output,
            "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

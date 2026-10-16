"""Markdown + JSON run reports, written under .promptci/reports/."""

from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .runner import RunResult

_MAX_OUTPUT_CHARS = 2000


def write_reports(result: RunResult, project_dir: Path) -> tuple[Path, Path]:
    slug = re.sub(r"[^a-z0-9-]+", "-", result.workflow.name.lower()).strip("-") or "run"
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = Path(project_dir) / ".promptci" / "reports"
    base.mkdir(parents=True, exist_ok=True)
    md_path = base / f"{slug}-{ts}.md"
    json_path = base / f"{slug}-{ts}.json"

    md_path.write_text(_markdown(result), encoding="utf-8")
    json_path.write_text(
        json.dumps(_structured(result), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return md_path, json_path


def _markdown(result: RunResult) -> str:
    wf = result.workflow
    lines = [
        f"# PromptCI run — {wf.name}",
        "",
        f"- started: {result.started_at}",
        f"- provider: {result.provider_label}",
        f"- result: **{'PASS' if result.ok else 'FAIL'}** ({result.duration_ms} ms)",
        "",
        "| step | status | checks | drift | time |",
        "|------|--------|--------|-------|------|",
    ]
    for o in result.outcomes:
        passed = sum(1 for c in o.checks if c.passed)
        drift = o.drift or "-"
        if drift == "same":
            drift = "-"
        lines.append(f"| {o.id} | {o.status.upper()} | {passed}/{len(o.checks)} | {drift} | {o.duration_ms} ms |")

    for o in result.outcomes:
        lines += ["", f"## {o.id} — {o.status.upper()} (model: {o.model or 'n/a'})"]
        if o.error:
            lines.append(f"- error: {o.error}")
        if o.drift and o.drift not in ("same", "new"):
            lines.append(f"- snapshot drift: {o.drift}")
        for c in o.checks:
            mark = "PASS" if c.passed else "FAIL"
            score = f" (score {c.score:.2f})" if c.score is not None else ""
            lines.append(f"- {mark} `{c.type}`{score}: {c.detail}")
        if o.status != "skipped" and o.output:
            snippet = o.output[:_MAX_OUTPUT_CHARS]
            if len(o.output) > _MAX_OUTPUT_CHARS:
                snippet += "\n... (truncated)"
            lines += ["", "<details><summary>output</summary>", "", "```text", snippet, "```", "", "</details>"]
    return "\n".join(lines) + "\n"


def _structured(result: RunResult) -> dict:
    return {
        "workflow": result.workflow.name,
        "started_at": result.started_at,
        "ok": result.ok,
        "duration_ms": result.duration_ms,
        "provider": result.provider_label,
        "steps": [asdict(o) for o in result.outcomes],
    }

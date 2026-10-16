"""`promptci doctor` — environment checks without running a full workflow."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .providers import list_models
from .schema import Workflow
from .templating import RunContext, interpolate, make_env, render_prompt


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(wf: Workflow, project_dir: Path) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("workflow parses", True, f"'{wf.name}', {len(wf.steps)} step(s)"))

    # Prompt files exist
    missing = [s.prompt for s in wf.steps if not (project_dir / s.prompt).is_file()]
    checks.append(
        Check(
            "prompt files",
            not missing,
            "all present" if not missing else f"missing: {', '.join(missing)}",
        )
    )

    # Interpolation + template render dry-run (earlier step outputs replaced by placeholders)
    env = make_env(project_dir)
    ctx = RunContext(inputs=wf.inputs)
    render_errors: list[str] = []
    for step in wf.steps:
        try:
            step_inputs = interpolate(step.inputs, ctx)
            variables = {
                **wf.inputs,
                **step_inputs,
                "steps": {sid: {"output": out} for sid, out in ctx.steps.items()},
            }
            render_prompt(env, step.prompt, variables)
        except Exception as e:  # ConfigError or jinja error — both are doctor findings
            render_errors.append(f"step '{step.id}': {e}")
        finally:
            ctx.steps[step.id] = "<sample output>"
    checks.append(
        Check(
            "interpolation & templates",
            not render_errors,
            "clean" if not render_errors else "; ".join(render_errors),
        )
    )

    # Model server reachable + configured models present
    base = wf.defaults.base_url
    if base.startswith("mock"):
        checks.append(Check("model server", True, "mock provider — runs fully offline"))
    else:
        api_key = os.environ.get(wf.defaults.api_key_env or "", "") or os.environ.get(
            "OPENAI_API_KEY", ""
        )
        targets = sorted({s.model or wf.defaults.model for s in wf.steps})
        try:
            models = list_models(base, api_key=api_key or None)
            missing_models = [
                t for t in targets if not any(mid == t or mid.split(":")[0] == t for mid in models)
            ]
            if not models:
                checks.append(
                    Check("model server", False, f"reachable but no models installed (try: ollama pull {targets[0]})")
                )
            elif missing_models:
                checks.append(
                    Check(
                        "model server",
                        False,
                        f"reachable at {base}; available: {', '.join(models[:8])}; "
                        f"missing: {', '.join(missing_models)}",
                    )
                )
            else:
                checks.append(
                    Check(
                        "model server",
                        True,
                        f"reachable at {base}; {len(models)} model(s), all configured models present",
                    )
                )
        except Exception as e:
            checks.append(Check("model server", False, str(e)))

    # Snapshots directory writable
    try:
        snap_dir = project_dir / ".promptci" / "snapshots"
        snap_dir.mkdir(parents=True, exist_ok=True)
        probe = snap_dir / ".probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(Check("snapshots dir", True, f"writable: {snap_dir}"))
    except OSError as e:
        checks.append(Check("snapshots dir", False, str(e)))

    return checks

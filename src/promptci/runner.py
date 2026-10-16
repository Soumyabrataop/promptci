"""Executes a workflow: interpolate inputs -> render prompt -> call model -> run checks -> snapshots."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any

from .assertions import AssertionResult, evaluate_checks
from .errors import PromptCIError
from .judge import judge_output
from .providers import BaseProvider, make_provider
from .schema import Workflow
from .snapshots import Drift, SnapshotStore, signature_of, snapshots_file
from .templating import RunContext, interpolate, make_env, render_prompt


@dataclass
class StepOutcome:
    id: str
    status: str  # "pass" | "fail" | "error" | "skipped"
    model: str = ""
    output: str = ""
    rendered_prompt: str = ""
    checks: list[AssertionResult] = field(default_factory=list)
    drift: Drift | None = None
    duration_ms: int = 0
    error: str | None = None


@dataclass
class RunResult:
    workflow: Workflow
    outcomes: list[StepOutcome]
    ok: bool
    provider_label: str
    started_at: str
    duration_ms: int
    snapshots_path: Path | None


def run_workflow(
    wf: Workflow,
    project_dir: Path,
    *,
    frozen: bool = False,
    var_overrides: dict[str, Any] | None = None,
    only_step: str | None = None,
    fail_fast: bool = False,
    provider: BaseProvider | None = None,
) -> RunResult:
    provider = provider or make_provider(wf.defaults)
    env = make_env(project_dir)
    inputs = {**wf.inputs, **(var_overrides or {})}
    ctx = RunContext(inputs=inputs)
    store = SnapshotStore(snapshots_file(project_dir, wf.name))

    outcomes: list[StepOutcome] = []
    ok = True
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_t0 = time.perf_counter()

    for idx, step in enumerate(wf.steps):
        if only_step and step.id != only_step:
            outcomes.append(StepOutcome(id=step.id, status="skipped"))
            continue

        t0 = time.perf_counter()
        model = step.model or wf.defaults.model
        try:
            step_inputs = interpolate(step.inputs, ctx)
            variables = {
                **inputs,
                **step_inputs,
                "steps": {sid: {"output": out} for sid, out in ctx.steps.items()},
            }
            rendered = render_prompt(env, step.prompt, variables)
            temperature = wf.defaults.temperature if step.temperature is None else step.temperature
            output = provider.complete(
                model=model,
                system=None,
                user=rendered,
                temperature=temperature,
                timeout=wf.defaults.timeout,
            )

            judge_model = wf.defaults.judge_model or model
            judge_fn = partial(judge_output, provider, judge_model)

            checks = evaluate_checks(step.checks, output, judge_fn)

            signature = signature_of(rendered, model, step_inputs)
            drift = store.compare(step.id, signature, output)
            if not frozen:
                store.record(step.id, signature, model, output)

            status = "fail" if any(not c.passed for c in checks) else "pass"
            if frozen and drift in ("output_drift", "signature_drift"):
                status = "fail"
            ctx.steps[step.id] = output
        except PromptCIError as e:
            outcomes.append(
                StepOutcome(
                    id=step.id,
                    status="error",
                    model=model,
                    error=str(e),
                    duration_ms=int((time.perf_counter() - t0) * 1000),
                )
            )
            ok = False
            if fail_fast:
                break
            continue

        outcomes.append(
            StepOutcome(
                id=step.id,
                status=status,
                model=model,
                output=output,
                rendered_prompt=rendered,
                checks=checks,
                drift=drift,
                duration_ms=int((time.perf_counter() - t0) * 1000),
            )
        )
        if status != "pass":
            ok = False
            if fail_fast:
                break

    return RunResult(
        workflow=wf,
        outcomes=outcomes,
        ok=ok,
        provider_label=provider.name,
        started_at=started_at,
        duration_ms=int((time.perf_counter() - run_t0) * 1000),
        snapshots_path=store.path if store.data else None,
    )

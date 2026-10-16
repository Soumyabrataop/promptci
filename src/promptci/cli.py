"""PromptCI command-line interface."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CI for LLM workflows: YAML pipelines, prompt templates, and regression gates.",
)

INIT_WORKFLOW = """\
name: onboarding-email
description: Demo workflow that runs fully offline with the built-in mock provider.
defaults:
  base_url: mock://  # swap to http://localhost:11434/v1 and model: llama3.2 for Ollama
  model: mock
inputs:
  product: PromptCI
steps:
  - id: draft
    prompt: prompts/draft.md
    checks:
      - type: not_contains
        value: ["TODO", "PLACEHOLDER", "lorem ipsum"]
      - type: max_length
        value: 2000
  - id: review
    prompt: prompts/review.md
    inputs:
      draft: ${{ steps.draft.output }}
    checks:
      - type: regex
        pattern: "(?i)ready to send"
      - type: llm_judge
        rubric: Does the review confirm the email draft is ready to send?
        threshold: 0.5
"""

INIT_DRAFT = """\
You are drafting a short onboarding email for a new user of {{ product }}.

Keep it friendly, under 120 words, and free of placeholders.

MOCK_RESPONSE: Hi there!

Welcome to {{ product }} — we're really glad you're here.
Your workspace is ready; the first thing to try is running `promptci run`
from your project folder. If anything looks off, `promptci doctor` will
point at the problem. Ready when you are!
"""

INIT_REVIEW = """\
You are reviewing an onboarding email draft before it is sent.

Draft:
{{ draft }}

Confirm the draft is friendly, clear, and has no placeholders.

MOCK_RESPONSE: The draft is friendly and clear, with no placeholders. Ready to send.
"""


@app.command()
def run(
    workflow: Path | None = typer.Argument(
        None, help="Path to a workflow file (default: ./promptci.yaml)"
    ),
    frozen: bool = typer.Option(
        False, "--frozen", help="Fail if any step drifts from its snapshot baseline (use in CI)."
    ),
    step: str | None = typer.Option(None, "--step", help="Run a single step by id."),
    var: list[str] | None = typer.Option(
        None, "--var", help="Override a workflow input, e.g. --var product=Acme (repeatable)."
    ),
    fail_fast: bool = typer.Option(False, "--fail-fast", help="Stop at the first failing step."),
    report: bool = typer.Option(True, "--report/--no-report", help="Write a run report."),
) -> None:
    """Run a workflow: render prompts, call the model, and gate on checks + snapshots."""
    from . import loader, runner
    from . import report as reporting

    try:
        wf_path = loader.find_workflow_file(workflow)
        wf, project_dir = loader.load_workflow(wf_path)
        result = runner.run_workflow(
            wf,
            project_dir,
            frozen=frozen,
            var_overrides=_parse_vars(var or []),
            only_step=step,
            fail_fast=fail_fast,
        )
    except Exception as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    _print_run(result)
    if report:
        md_path, _ = reporting.write_reports(result, project_dir)
        typer.echo(f"report: {md_path}")
    if not result.ok:
        raise typer.Exit(1)


@app.command()
def validate(
    workflow: Path | None = typer.Argument(
        None, help="Path to a workflow file (default: ./promptci.yaml)"
    ),
) -> None:
    """Validate a workflow file without calling any model (free)."""
    from .loader import load_workflow, validate_structure

    try:
        wf_path = find_and_load(workflow, load_workflow)
    except Exception as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    wf, project_dir = wf_path
    errors, warnings = validate_structure(wf, project_dir)
    for err in errors:
        typer.secho(f"  [error]   {err}", fg=typer.colors.RED)
    for warn in warnings:
        typer.secho(f"  [warning] {warn}", fg=typer.colors.YELLOW)
    if errors:
        typer.secho(f"invalid: {len(errors)} error(s)", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    typer.secho(
        f"valid: '{wf.name}' with {len(wf.steps)} step(s)"
        + (f", {len(warnings)} warning(s)" if warnings else ""),
        fg=typer.colors.GREEN,
    )


@app.command()
def doctor(
    workflow: Path | None = typer.Argument(
        None, help="Path to a workflow file (default: ./promptci.yaml)"
    ),
) -> None:
    """Check the environment: workflow, templates, references, model server, snapshots."""
    from . import doctor as doctor_mod
    from .loader import load_workflow

    try:
        wf, project_dir = find_and_load(workflow, load_workflow)
    except Exception as e:
        typer.secho(f"error: {e}", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)

    typer.echo(f"PromptCI doctor — {wf_path_display(workflow)}")
    checks = doctor_mod.run_doctor(wf, project_dir)
    for check in checks:
        color = typer.colors.GREEN if check.ok else typer.colors.RED
        mark = "ok  " if check.ok else "FAIL"
        typer.secho(f"  [{mark}] {check.name:<26} {check.detail}", fg=color)
    failed = sum(1 for c in checks if not c.ok)
    if failed:
        typer.secho(f"\n{failed}/{len(checks)} checks failed", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    typer.secho(f"\n{len(checks)}/{len(checks)} checks passed", fg=typer.colors.GREEN)


@app.command()
def init(
    directory: Path = typer.Option(Path("."), "--dir", help="Where to scaffold the project."),
) -> None:
    """Scaffold a starter workflow that runs offline with the mock provider."""
    target = Path(directory)
    wf_file = target / "promptci.yaml"
    if wf_file.exists():
        typer.secho("error: promptci.yaml already exists here", fg=typer.colors.RED, err=True)
        raise typer.Exit(2)
    (target / "prompts").mkdir(parents=True, exist_ok=True)
    wf_file.write_text(INIT_WORKFLOW, encoding="utf-8")
    (target / "prompts" / "draft.md").write_text(INIT_DRAFT, encoding="utf-8")
    (target / "prompts" / "review.md").write_text(INIT_REVIEW, encoding="utf-8")
    typer.secho("scaffolded:", fg=typer.colors.GREEN)
    for rel in ("promptci.yaml", "prompts/draft.md", "prompts/review.md"):
        typer.echo(f"  {target / rel}")
    typer.echo("\nnext: promptci run   (runs offline with the mock provider)")


def find_and_load(explicit: Path | None, load_fn) -> tuple:
    from .loader import find_workflow_file

    return load_fn(find_workflow_file(explicit))


def wf_path_display(explicit: Path | None) -> str:
    return str(explicit) if explicit else "promptci.yaml"


def _parse_vars(pairs: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in pairs:
        if "=" not in pair:
            raise ValueError(f"--var expects name=value, got '{pair}'")
        name, value = pair.split("=", 1)
        out[name] = value
    return out


def _print_run(result) -> None:
    total = len(result.outcomes)
    typer.secho(
        f"workflow: {result.workflow.name}  (provider: {result.provider_label})", bold=True
    )
    labels = {"pass": "PASS", "fail": "FAIL", "error": "ERR!", "skipped": "SKIP"}
    colors = {
        "pass": typer.colors.GREEN,
        "fail": typer.colors.RED,
        "error": typer.colors.RED,
        "skipped": typer.colors.YELLOW,
    }
    for i, o in enumerate(result.outcomes, 1):
        passed_checks = sum(1 for c in o.checks if c.passed)
        checks_s = f"{passed_checks}/{len(o.checks)} checks" if o.checks else ""
        drift_s = f"  drift: {o.drift}" if o.drift not in (None, "same", "new") else ""
        typer.secho(
            f"  [{i}/{total}] {o.id:<16} {labels[o.status]:<4} {checks_s:<14} "
            f"{o.duration_ms:>5} ms{drift_s}",
            fg=colors[o.status],
        )
        if o.error:
            typer.secho(f"        {o.error}", fg=typer.colors.RED)
        for c in o.checks:
            if not c.passed:
                typer.secho(f"        [fail] {c.type}: {c.detail}", fg=typer.colors.RED)
    drift_steps = [
        o.id for o in result.outcomes if o.drift in ("output_drift", "signature_drift")
    ]
    typer.echo("")
    if drift_steps and not result.ok:
        typer.secho(
            f"snapshot drift on: {', '.join(drift_steps)} — "
            "re-run without --frozen to re-baseline",
            fg=typer.colors.YELLOW,
        )
    typer.secho(
        f"result: {'PASS' if result.ok else 'FAIL'}",
        bold=True,
        fg=typer.colors.GREEN if result.ok else typer.colors.RED,
    )


def main() -> None:
    app()


if __name__ == "__main__":
    main()

# PromptCI

**CI for LLM workflows: YAML pipelines, prompt templates, and regression gates — running on open-weight models, on your laptop.**

Prompts are code. They break silently. PromptCI treats them like code: describe your LLM workflow in YAML, keep prompts in versioned template files, and gate every change with assertions and output snapshots. Edit a prompt, run `promptci run --frozen`, and find out immediately whether the model's behavior drifted — instead of hearing about it from a user.

Built on open source end to end: PromptCI is MIT-licensed, and by default it talks to **Ollama**, so your workflows run on open-weight models (Llama, Qwen, Mistral, Gemma…) with **no API keys, no cloud bills, and no data leaving your machine**. It works fully offline — `promptci init` scaffolds a demo that runs with the built-in mock provider and zero network.

## Why open matters here

- **Runs on a laptop with no internet.** Ollama + the mock provider mean you can author, validate, and regression-test prompts on a plane.
- **Keeps data off servers you don't control.** Prompts often embed customer text. With local inference, nothing is ever sent anywhere.
- **Costs nothing to run.** Regression-testing prompts on every commit is only practical if each run is free. With open models, it is.
- **Swap models freely.** Everything speaks the OpenAI-compatible dialect, so changing `model:` in one YAML line moves you between llama3.2, qwen2.5, mistral — or a cloud API when you want one. Locked-in pricing isn't part of the design.

## Quickstart

```bash
pip install git+https://github.com/Soumyabrataop/promptci.git   # or: pip install -e . from a clone
promptci init          # scaffold a demo workflow (runs offline via the mock provider)
promptci run           # run it — snapshots are recorded on first run
promptci run --frozen  # CI mode: fail if any output drifted from its baseline
```

With Ollama (`ollama pull llama3.2` first), point your workflow at it:

```yaml
defaults:
  base_url: http://localhost:11434/v1
  model: llama3.2
```

See [examples/ollama-demo](examples/ollama-demo) for a complete local-model workflow, and [examples/github-workflow.yml](examples/github-workflow.yml) for running PromptCI in GitHub Actions with Ollama on the runner.

## Commands

| Command | What it does |
|---|---|
| `promptci run [FILE]` | Execute the workflow. `--frozen` fails on snapshot drift (CI mode), `--step ID` runs one step, `--var k=v` overrides inputs, `--fail-fast` stops at the first failure. |
| `promptci validate [FILE]` | Schema + structural checks (missing prompt files, forward references, unknown inputs). Never calls a model — free. |
| `promptci doctor [FILE]` | Environment checks: workflow parses, templates render, references resolve, model server reachable, configured models installed, snapshots writable. |
| `promptci init` | Scaffold a starter workflow that runs fully offline. |

Exit codes: `0` pass, `1` checks/drift failed, `2` configuration error — so it drops straight into any CI system.

## Workflow format

```yaml
name: onboarding-email
defaults:
  base_url: http://localhost:11434/v1   # any OpenAI-compatible server, or "mock://" for offline
  model: llama3.2
  judge_model: llama3.2                 # optional: model used for llm_judge checks
  temperature: 0.2
inputs:
  product: PromptCI                     # overridable with --var product=Acme
steps:
  - id: draft
    prompt: prompts/draft.md            # a jinja2 template, relative to this file
    checks:
      - type: not_contains
        value: ["TODO", "PLACEHOLDER"]
      - type: max_length
        value: 2000
  - id: review
    prompt: prompts/review.md
    inputs:
      draft: ${{ steps.draft.output }}  # previous step's output becomes this step's input
    checks:
      - type: regex
        pattern: "(?i)ready to send"
      - type: json_schema               # output must parse as JSON with these keys/types
        schema:
          type: object
          required: [verdict]
          properties: { verdict: { type: string } }
      - type: llm_judge                 # semantic gate: a model scores against the rubric
        rubric: Is the review specific and does it confirm the email is ready?
        threshold: 0.7
```

Prompt templates are plain markdown with jinja2 variables (`{{ product }}`), and can `{% include %}` each other — so shared instructions live in one versioned file.

### References

Inside `inputs` you can use:

- `${{ inputs.name }}` — workflow inputs (or `--var` overrides)
- `${{ steps.<id>.output }}` — a previous step's raw output
- `${{ steps.<id>.json.<path> }}` — a previous step's output parsed as JSON
- `${{ env.NAME }}` — environment variables

### Checks

| Type | Free | What it does |
|---|---|---|
| `contains` / `not_contains` | yes | substring(s) must / must not appear |
| `regex` | yes | pattern must match |
| `min_length` / `max_length` | yes | output length bounds |
| `json_schema` | yes | output must be JSON with required keys and declared types |
| `llm_judge` | model call | a model scores 0–1 against your `rubric`; must meet `threshold` |

### Snapshot regression gates

Every step's snapshot (hash of rendered prompt + model + resolved inputs, plus the output) is stored in `.promptci/snapshots/` — commit that folder. A plain `promptci run` re-baselines as you iterate; `promptci run --frozen` fails on any drift. If you intentionally changed a prompt, take the new baseline and commit it; if you didn't, something changed under you and CI just caught it.

## Development

```bash
pip install -e ".[dev]"
pytest -q        # the whole suite runs offline against the mock provider
ruff check src tests
```

## Roadmap

- Parallel / DAG step execution
- Token-usage and latency tracking in reports
- Fuzzy snapshot comparison (semantic drift scoring instead of exact match)
- First-class GitHub Action

## License

MIT — see [LICENSE](LICENSE).

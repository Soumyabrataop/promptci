"""Pydantic schema for PromptCI workflow files."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

CheckType = Literal[
    "contains",
    "not_contains",
    "regex",
    "json_schema",
    "min_length",
    "max_length",
    "llm_judge",
]


class CheckSpec(BaseModel):
    type: CheckType
    # contains/not_contains: str or list[str]; min_length/max_length: int
    value: Any = None
    pattern: str | None = None  # regex
    json_schema: dict[str, Any] | None = Field(default=None, alias="schema")  # json_schema
    rubric: str | None = None  # llm_judge
    threshold: float = 0.7  # llm_judge

    model_config = ConfigDict(populate_by_name=True)


class Defaults(BaseModel):
    model: str = "llama3.2"
    base_url: str = "http://localhost:11434/v1"
    api_key_env: str | None = None
    judge_model: str | None = None
    temperature: float = 0.2
    timeout: float = 120.0


class StepSpec(BaseModel):
    id: str
    prompt: str  # path to a template file, relative to the workflow file
    model: str | None = None
    temperature: float | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    checks: list[CheckSpec] = Field(
        default_factory=list,
        validation_alias=AliasChoices("checks", "assert", "assertions"),
    )

    @field_validator("id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not v or any(c.isspace() for c in v):
            raise ValueError("step id must be non-empty and contain no whitespace")
        return v


class Workflow(BaseModel):
    name: str
    description: str | None = None
    defaults: Defaults = Field(default_factory=Defaults)
    inputs: dict[str, Any] = Field(default_factory=dict)
    steps: list[StepSpec] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_step_ids(self) -> Workflow:
        seen: set[str] = set()
        for step in self.steps:
            if step.id in seen:
                raise ValueError(f"duplicate step id '{step.id}'")
            seen.add(step.id)
        return self

"""PromptCI error types. All are subclasses of PromptCIError so the runner can catch broadly."""


class PromptCIError(Exception):
    """Base class for all PromptCI errors."""


class ConfigError(PromptCIError):
    """A workflow file, template, or reference is invalid."""


class ProviderError(PromptCIError):
    """The model server could not be reached or returned an error."""


class JudgeError(PromptCIError):
    """The LLM judge returned something we could not parse as a score."""

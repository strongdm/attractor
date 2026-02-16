"""Model catalog: ModelInfo and lookup functions."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelInfo:
    """Metadata about an LLM model."""

    id: str
    provider: str
    display_name: str
    context_window: int
    max_output: int | None = None
    supports_tools: bool = True
    supports_vision: bool = False
    supports_reasoning: bool = False
    input_cost_per_million: float | None = None
    output_cost_per_million: float | None = None
    aliases: list[str] = field(default_factory=list)


# Current model catalog
MODELS: list[ModelInfo] = [
    # Anthropic
    ModelInfo(
        id="claude-opus-4-6",
        provider="anthropic",
        display_name="Claude Opus 4.6",
        context_window=200_000,
        max_output=32_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=15.0,
        output_cost_per_million=75.0,
    ),
    ModelInfo(
        id="claude-sonnet-4-5-20250929",
        provider="anthropic",
        display_name="Claude Sonnet 4.5",
        context_window=200_000,
        max_output=16_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=3.0,
        output_cost_per_million=15.0,
        aliases=["claude-sonnet-4-5"],
    ),
    ModelInfo(
        id="claude-haiku-4-5-20251001",
        provider="anthropic",
        display_name="Claude Haiku 4.5",
        context_window=200_000,
        max_output=8_192,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=False,
        input_cost_per_million=0.8,
        output_cost_per_million=4.0,
        aliases=["claude-haiku-4-5"],
    ),
    # OpenAI
    ModelInfo(
        id="gpt-5.2",
        provider="openai",
        display_name="GPT-5.2",
        context_window=256_000,
        max_output=32_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=2.5,
        output_cost_per_million=10.0,
    ),
    ModelInfo(
        id="gpt-5.2-mini",
        provider="openai",
        display_name="GPT-5.2 Mini",
        context_window=256_000,
        max_output=16_000,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=0.75,
        output_cost_per_million=3.0,
    ),
    ModelInfo(
        id="gpt-5.2-codex",
        provider="openai",
        display_name="GPT-5.2 Codex",
        context_window=256_000,
        max_output=32_000,
        supports_tools=True,
        supports_vision=False,
        supports_reasoning=True,
        input_cost_per_million=2.5,
        output_cost_per_million=10.0,
    ),
    # Gemini
    ModelInfo(
        id="gemini-3-pro-preview",
        provider="gemini",
        display_name="Gemini 3 Pro Preview",
        context_window=2_000_000,
        max_output=65_536,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=1.25,
        output_cost_per_million=10.0,
    ),
    ModelInfo(
        id="gemini-3-flash-preview",
        provider="gemini",
        display_name="Gemini 3 Flash Preview",
        context_window=1_000_000,
        max_output=65_536,
        supports_tools=True,
        supports_vision=True,
        supports_reasoning=True,
        input_cost_per_million=0.15,
        output_cost_per_million=0.6,
    ),
]

# Build lookup indices
_by_id: dict[str, ModelInfo] = {m.id: m for m in MODELS}
_by_alias: dict[str, ModelInfo] = {}
for _m in MODELS:
    for _a in _m.aliases:
        _by_alias[_a] = _m


def get_model_info(model_id: str) -> ModelInfo | None:
    """Look up a model by its ID or alias. Returns None if not found."""
    return _by_id.get(model_id) or _by_alias.get(model_id)


def list_models(
    *,
    provider: str | None = None,
    supports_reasoning: bool | None = None,
    supports_tools: bool | None = None,
    supports_vision: bool | None = None,
) -> list[ModelInfo]:
    """List models, optionally filtered by provider and capabilities."""
    result = MODELS
    if provider is not None:
        result = [m for m in result if m.provider == provider]
    if supports_reasoning is not None:
        result = [m for m in result if m.supports_reasoning == supports_reasoning]
    if supports_tools is not None:
        result = [m for m in result if m.supports_tools == supports_tools]
    if supports_vision is not None:
        result = [m for m in result if m.supports_vision == supports_vision]
    return result

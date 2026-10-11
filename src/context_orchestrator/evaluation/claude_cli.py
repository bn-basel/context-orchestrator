"""Parse usage data from ``claude -p --output-format json`` results.

What the installed Claude Code CLI exposes (checked against v2.1.292, see
docs/benchmark-methodology.md): per-model input, output, cache-read,
cache-creation and thinking token counts; wall-clock and API durations; and a
``costUSD`` value with ``costBasis: "list"``. That cost is an API-list-price
equivalent computed by the CLI. On a subscription it is NOT what the user is
charged, so it is recorded as an estimate and labelled as such.

Missing fields become ``Metric.unavailable`` and are never treated as zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from context_orchestrator.models import Metric, MetricKind

_TOKEN_FIELDS = {
    # RunUsage attribute: modelUsage key
    "input_tokens": "inputTokens",
    "output_tokens": "outputTokens",
    "cache_read_input_tokens": "cacheReadInputTokens",
    "cache_creation_input_tokens": "cacheCreationInputTokens",
    "thinking_tokens": "thinkingTokens",
}


@dataclass(slots=True)
class RunUsage:
    models: list[str]
    input_tokens: Metric
    output_tokens: Metric
    cache_read_input_tokens: Metric
    cache_creation_input_tokens: Metric
    thinking_tokens: Metric
    duration_ms: Metric
    duration_api_ms: Metric
    api_equivalent_cost_usd: Metric
    num_turns: int | None
    is_error: bool | None
    notes: list[str] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> Metric:
        """Uncached + cache-read + cache-creation input; unavailable if any part is."""
        parts = [self.input_tokens, self.cache_read_input_tokens, self.cache_creation_input_tokens]
        if any(p.kind is MetricKind.UNAVAILABLE for p in parts):
            return Metric.unavailable("one or more input token components unavailable")
        return Metric.measured(
            sum(int(p.value or 0) for p in parts),
            "sum of uncached, cache-read and cache-creation input tokens",
        )


def _sum_model_field(model_usage: dict[str, Any], key: str) -> Metric:
    values = [m.get(key) for m in model_usage.values()]
    if not values or any(not isinstance(v, int | float) for v in values):
        return Metric.unavailable(f"modelUsage.*.{key} missing")
    return Metric.measured(sum(values), f"claude-cli modelUsage.*.{key} (reported by API)")


def parse_claude_cli_result(data: dict[str, Any]) -> RunUsage:
    model_usage = data.get("modelUsage")
    notes: list[str] = []
    if not isinstance(model_usage, dict) or not model_usage:
        model_usage = {}
        notes.append("modelUsage missing: token metrics unavailable")

    tokens = {
        attr: _sum_model_field(model_usage, key)
        if model_usage
        else Metric.unavailable("modelUsage missing")
        for attr, key in _TOKEN_FIELDS.items()
    }

    costs = [m.get("costUSD") for m in model_usage.values()]
    bases = sorted({str(m.get("costBasis", "unknown")) for m in model_usage.values()})
    if costs and all(isinstance(c, int | float) for c in costs):
        cost = Metric.estimated(
            round(sum(costs), 6),
            f"claude-cli modelUsage.*.costUSD, costBasis={','.join(bases)}; API-equivalent "
            "price computed by the CLI, not a subscription charge",
        )
    else:
        cost = Metric.unavailable("costUSD missing")

    def duration(key: str) -> Metric:
        value = data.get(key)
        if isinstance(value, int | float):
            return Metric.measured(value, f"claude-cli {key}")
        return Metric.unavailable(f"{key} missing")

    return RunUsage(
        models=sorted(model_usage),
        duration_ms=duration("duration_ms"),
        duration_api_ms=duration("duration_api_ms"),
        api_equivalent_cost_usd=cost,
        num_turns=data.get("num_turns"),
        is_error=data.get("is_error"),
        notes=notes,
        **tokens,
    )

import json
from pathlib import Path

from context_orchestrator.evaluation.claude_cli import parse_claude_cli_result
from context_orchestrator.models import MetricKind

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "claude_cli_result.json"


def test_parses_a_real_cli_result() -> None:
    # Captured from `claude -p "Reply with the single word OK" --output-format json --model haiku`
    # (Claude Code 2.1.292), with session ids replaced.
    usage = parse_claude_cli_result(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert usage.models == ["claude-haiku-4-5-20251001"]
    assert usage.input_tokens.value == 10
    assert usage.output_tokens.value == 40
    assert usage.cache_read_input_tokens.value == 26621
    assert usage.cache_creation_input_tokens.value == 8704
    assert usage.total_input_tokens.value == 10 + 26621 + 8704
    assert usage.input_tokens.kind is MetricKind.MEASURED
    assert usage.duration_ms.kind is MetricKind.MEASURED

    # The CLI's cost is a list-price equivalent, so it is an estimate, never "measured".
    assert usage.api_equivalent_cost_usd.kind is MetricKind.ESTIMATED
    assert "costBasis=list" in usage.api_equivalent_cost_usd.method
    assert "not a subscription charge" in usage.api_equivalent_cost_usd.method


def test_missing_usage_is_unavailable_not_zero() -> None:
    usage = parse_claude_cli_result({"type": "result", "is_error": True})
    for metric in (
        usage.input_tokens,
        usage.output_tokens,
        usage.api_equivalent_cost_usd,
        usage.duration_ms,
        usage.total_input_tokens,
    ):
        assert metric.kind is MetricKind.UNAVAILABLE
        assert metric.value is None
    assert usage.notes


def test_partial_usage_does_not_produce_a_total() -> None:
    data = {"modelUsage": {"m": {"inputTokens": 5, "outputTokens": 1}}}
    usage = parse_claude_cli_result(data)
    assert usage.input_tokens.value == 5
    assert usage.cache_read_input_tokens.kind is MetricKind.UNAVAILABLE
    assert usage.total_input_tokens.kind is MetricKind.UNAVAILABLE

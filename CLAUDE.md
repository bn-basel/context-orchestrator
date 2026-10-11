# Context Orchestrator: notes for AI agents

- Python 3.11+, standard library only at runtime. Dev: `uv sync`, `uv run pytest`, `uv run ruff check .`,
  `uv run ruff format .`.
- Layout and design decisions: `docs/architecture.md`. Benchmark rules: `docs/benchmark-methodology.md`.
- Never claim benchmark results that are not backed by raw files under `benchmarks/results/`.
- Any number must say whether it is measured, estimated or unavailable (`models.Metric`); missing is not zero.
- Telemetry must not store task text, retrieved text or secrets unless explicitly opted in.
- The service only reads project files; state lives in `.ctxo/`. Keep it that way.
- `examples/sample_project` is a test fixture: changing it can change test expectations.

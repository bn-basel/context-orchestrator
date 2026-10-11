---
kind: convention
status: verified
---
# Coding conventions

## Python style
- Python 3.11+, type hints on every public function.
- Plain functions and dataclasses; no classes with hidden state.
- Raise `ShelfwiseError` subclasses for domain errors; never return `None` to
  signal failure.

## Naming
- Money variables and columns end in `_cents` (see ADR 0004).
- Timestamps end in `_at`, calendar dates end in `_on`.

## Tests
- pytest, one test module per source module (`tests/test_<module>.py`).
- Use fixed timestamps; never call `datetime.now()` inside tests. Pass a
  `now` argument to functions that need the current time.

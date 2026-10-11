"""Token estimation.

The context service never sees a model's tokenizer, so any token count it
produces is an estimate and is labelled as one. Real counts come from the
model provider's usage data during benchmark runs (see ``evaluation``).
"""

from __future__ import annotations

import math

CHARS_PER_TOKEN = 4
ESTIMATE_METHOD = "ceil(chars / 4) heuristic, not a model tokenizer"


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / CHARS_PER_TOKEN) if text else 0

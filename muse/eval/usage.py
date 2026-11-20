"""Token usage and cost tracking for live eval runs."""

from __future__ import annotations

from collections import Counter, defaultdict
from types import SimpleNamespace

# USD per million tokens: (input, output, cache read, 5-minute cache write).
# Haiku 5.5's rate applies to prompts up to 100K tokens, which covers Muse.
PRICES = {
    "claude-sonnet-5-5": (2.00, 10.00, 0.20, 2.50),
    "claude-sonnet-5": (2.00, 10.00, 0.20, 2.50),
    "claude-haiku-5-5": (0.10, 0.50, 0.01, 0.125),
    "claude-opus-5-5": (4.00, 20.00, 0.20, 5.00),
}

FIELDS = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")


class UsageTrackingClient:
    """Wraps an Anthropic client and totals `usage` per model that served a response."""

    def __init__(self, client):
        self._client = client
        self.usage: dict[str, Counter] = defaultdict(Counter)
        self.messages = SimpleNamespace(create=self._wrap(client.messages.create))
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._wrap(client.beta.messages.create)))

    def _wrap(self, create):
        def tracked(**kwargs):
            response = create(**kwargs)
            counts = self.usage[response.model]
            counts["requests"] += 1
            for name in FIELDS:
                counts[name] += getattr(response.usage, name, 0) or 0
            return response
        return tracked

    def cost(self, model: str) -> float | None:
        price = PRICES.get(model)
        if price is None:
            return None
        u = self.usage[model]
        tokens = (u["input_tokens"], u["output_tokens"],
                  u["cache_read_input_tokens"], u["cache_creation_input_tokens"])
        return sum(t * p for t, p in zip(tokens, price)) / 1_000_000

    def report(self) -> str:
        lines = []
        total = 0.0
        for model, u in sorted(self.usage.items()):
            cost = self.cost(model)
            total += cost or 0
            lines.append(
                f"  {model:<20} {u['requests']:>4} req  in {u['input_tokens']:>8}  "
                f"out {u['output_tokens']:>7}  cache read {u['cache_read_input_tokens']:>8}  "
                f"write {u['cache_creation_input_tokens']:>7}  "
                + (f"${cost:.4f}" if cost is not None else "(no price on file)")
            )
        lines.append(f"  {'total':<20} ${total:.4f}")
        return "\n".join(lines)

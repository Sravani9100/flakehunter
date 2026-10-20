"""Shared Claude API settings and cost accounting."""

from dataclasses import dataclass
from typing import Any

import anthropic

from flakehunter.config import Settings

FALLBACK_BETA = "server-side-fallback-2026-07-01"

# USD per million tokens: (input, output, cache read). Cache writes bill at 1.25x input.
PRICES: dict[str, tuple[float, float, float]] = {
    "claude-opus-5-5": (4.0, 20.0, 0.20),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.01),
}


class RefusalError(RuntimeError):
    pass


def make_client(settings: Settings) -> anthropic.Anthropic:
    if settings.anthropic_api_key:
        return anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value())
    return anthropic.Anthropic()


def describe_error(exc: Exception) -> str:
    """A message for the dashboard. Tracebacks stay in the server log."""
    if isinstance(exc, anthropic.AuthenticationError) or "authentication method" in str(exc):
        return "No valid Anthropic API key: set ANTHROPIC_API_KEY where the API server runs."
    if "credit balance is too low" in str(exc):
        return "The Anthropic account is out of credits. Add credits under Plans & Billing."
    if isinstance(exc, anthropic.RateLimitError):
        return "Rate limited by the Anthropic API. Try again in a minute."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Couldn't reach the Anthropic API."
    return str(exc)[:500] or type(exc).__name__


def request_kwargs(settings: Settings) -> dict[str, Any]:
    """Arguments shared by every request to client.beta.messages."""
    kwargs: dict[str, Any] = {
        "model": settings.anthropic_model,
        "thinking": {"type": "adaptive", "display": "summarized"},
    }
    if settings.ai_fallbacks:
        kwargs["betas"] = [FALLBACK_BETA]
        kwargs["fallbacks"] = "default"
    return kwargs


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, model: str, usage: Any) -> None:
        uncached = usage.input_tokens or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
        output = usage.output_tokens or 0
        # A fallback can serve the request from another model; price by the model that ran.
        in_price, out_price, read_price = PRICES.get(model, PRICES["claude-opus-5-5"])
        self.input_tokens += uncached + cache_read + cache_write
        self.output_tokens += output
        self.cost_usd += (
            uncached * in_price
            + cache_write * in_price * 1.25
            + cache_read * read_price
            + output * out_price
        ) / 1_000_000

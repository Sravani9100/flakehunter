"""Root-cause a flaky test with one structured Claude call, streaming its reasoning."""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from flakehunter.config import Settings
from flakehunter.llm import RefusalError, Usage, request_kwargs
from flakehunter.models import Diagnosis

CATEGORIES = [
    "timing",
    "concurrency",
    "ordering",
    "randomness",
    "shared_state",
    "environment",
    "network",
    "resource_leak",
    "unknown",
]

CATEGORY_GUIDE = """Categories:
- timing: fixed sleeps, timeouts, or wall-clock thresholds racing real work
- concurrency: threads, async tasks, or processes interleaving without proper synchronization
- ordering: relying on an order that isn't guaranteed (set or dict iteration, directory \
listings, completion order, test execution order)
- randomness: unseeded or insufficiently constrained random values
- shared_state: state leaking between tests (globals, caches, files, environment variables, \
databases)
- environment: differences in machine, OS, timezone, locale, or installed tools
- network: real network calls, ports, DNS, or external services
- resource_leak: unclosed files, sockets, or threads exhausting resources
- unknown: none of the above fits"""

SYSTEM = f"""You diagnose flaky tests: tests that both pass and fail on the same code.

Given a test's CI history, failure output, and source, identify the single most likely root \
cause. Ground every claim in the provided code or output, and quote the specific lines as \
evidence. If the evidence doesn't support a confident answer, give a low confidence rather \
than guessing.

The suggested fix must remove the cause. Retrying, skipping, or lengthening a sleep hides a \
flake rather than fixing it.

{CATEGORY_GUIDE}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string", "enum": CATEGORIES},
        "confidence": {"type": "number", "description": "From 0 to 1."},
        "summary": {"type": "string", "description": "One sentence a developer can scan."},
        "explanation": {
            "type": "string",
            "description": "Markdown. How the flake happens, step by step.",
        },
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Specific code lines or output that support the diagnosis.",
        },
        "suggested_fix": {"type": "string", "description": "Markdown. The change to make."},
    },
    "required": ["category", "confidence", "summary", "explanation", "evidence", "suggested_fix"],
    "additionalProperties": False,
}


class DiagnosisResult(BaseModel):
    category: Literal[tuple(CATEGORIES)]  # type: ignore[valid-type]
    confidence: float
    summary: str
    explanation: str
    evidence: list[str]
    suggested_fix: str


@dataclass(frozen=True)
class ThinkingDelta:
    text: str


def run_diagnosis(
    client: Any, settings: Settings, test_case_id: int, context: str
) -> Iterator[ThinkingDelta | Diagnosis]:
    """Yield reasoning as it streams, then an unsaved Diagnosis."""
    started = time.monotonic()
    thinking: list[str] = []
    with client.beta.messages.stream(
        **request_kwargs(settings),
        max_tokens=32000,
        system=SYSTEM,
        output_config={
            "effort": settings.ai_effort,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        messages=[{"role": "user", "content": context}],
    ) as stream:
        for event in stream:
            if event.type == "content_block_delta" and event.delta.type == "thinking_delta":
                thinking.append(event.delta.thinking)
                yield ThinkingDelta(event.delta.thinking)
        message = stream.get_final_message()

    if message.stop_reason == "refusal":
        raise RefusalError("The model declined to diagnose this test.")
    if message.stop_reason == "max_tokens":
        raise RuntimeError("The diagnosis was cut off before it finished.")
    text = next(b.text for b in message.content if b.type == "text")
    result = DiagnosisResult.model_validate_json(text)

    usage = Usage()
    usage.add(message.model, message.usage)
    yield Diagnosis(
        test_case_id=test_case_id,
        category=result.category,
        confidence=min(max(result.confidence, 0.0), 1.0),
        summary=result.summary,
        explanation=result.explanation,
        evidence=result.evidence,
        suggested_fix=result.suggested_fix,
        thinking="".join(thinking) or None,
        model=message.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost_usd=usage.cost_usd,
        duration_s=time.monotonic() - started,
    )

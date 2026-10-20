"""Scripted stand-ins for the Anthropic client and the sandbox."""

import itertools
import json
from pathlib import Path
from types import SimpleNamespace as NS

from flakehunter.sandbox import RunStats

_ids = itertools.count(1)


def usage(input_tokens=1000, output_tokens=200):
    return NS(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_input_tokens=0,
        cache_creation_input_tokens=0,
    )


def text(value):
    return NS(type="text", text=value)


def thinking(value):
    return NS(type="thinking", thinking=value)


def tool_use(name, **tool_input):
    return NS(type="tool_use", name=name, input=tool_input, id=f"toolu_{next(_ids)}")


def message(*content, stop_reason="tool_use", model="claude-opus-5-5"):
    return NS(content=list(content), stop_reason=stop_reason, model=model, usage=usage())


class FakeStream:
    def __init__(self, events, final):
        self._events, self._final = events, final

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


class FakeMessages:
    def __init__(self):
        self.responses = []
        self.stream_script = None
        self.requests = []

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)

    def stream(self, **kwargs):
        self.requests.append(kwargs)
        events, final = self.stream_script
        return FakeStream(events, final)


class FakeClient:
    def __init__(self):
        self.beta = NS(messages=FakeMessages())

    @property
    def messages(self) -> FakeMessages:
        return self.beta.messages

    def script_diagnosis(self, result: dict, thoughts=("Looking at the sleep. ",), **kwargs):
        events = [
            NS(type="content_block_delta", delta=NS(type="thinking_delta", thinking=t))
            for t in thoughts
        ]
        final = message(text(json.dumps(result)), stop_reason="end_turn", **kwargs)
        self.messages.stream_script = (events, final)


class FakeSandbox:
    """Fails half the runs until the test file contains the marker "FIXED"."""

    def __init__(self, test_path="tests/test_clock.py"):
        self.test_path = test_path
        self.calls = []

    def run_test(self, workspace: Path, node_id: str, runs: int) -> RunStats:
        self.calls.append((node_id, runs))
        source = (workspace / self.test_path).read_text()
        failures = 0 if "FIXED" in source else runs // 2
        return RunStats(runs, failures, "AssertionError: not ready" if failures else None)


def make_repo(root: Path) -> Path:
    """A tiny project with one "flaky" test, laid out like a real repository."""
    (root / "app").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (root / "app" / "__init__.py").write_text("")
    (root / "app" / "clock.py").write_text(
        "import random\n\n\ndef ready():\n    return random.random() > 0.5\n"
    )
    (root / "tests" / "conftest.py").write_text("")
    (root / "tests" / "test_clock.py").write_text(
        "from app.clock import ready\n\n\ndef test_ready():\n    assert ready()\n"
    )
    return root

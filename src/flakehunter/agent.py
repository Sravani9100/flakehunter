"""The fix agent: a tool-use loop that edits code and reruns the test until it's reliable.

The agent's own runs are only a signal. The harness in fixes.py verifies independently,
with more runs, after the agent submits.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from flakehunter.config import Settings
from flakehunter.diagnosis import CATEGORIES, CATEGORY_GUIDE
from flakehunter.llm import RefusalError, Usage, request_kwargs
from flakehunter.sandbox import Sandbox
from flakehunter.testloc import TestLocation

MAX_READ_CHARS = 100_000
MAX_LISTED_FILES = 200
MAX_AGENT_RUNS = 30
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache"}

SYSTEM = f"""You fix flaky tests in a Python repository. A flaky test both passes and fails \
on the same code. Find the root cause and remove it.

Rules:
- Fix the cause, not the symptom. Never skip, xfail, retry, delete, or rename the test. \
Don't make a race pass by lengthening a sleep or timeout; wait for the actual condition.
- If the test asserts something the code never promised, fix the test so it checks the real \
contract, and say so in your explanation. If the code is wrong, fix the code.
- Make the smallest change that fixes the cause.
- Reproduce the flake with run_test first. After your change, confirm with run_test using at \
least 20 runs, then call submit_fix. If you can't find a fix, call submit_fix with \
fixed=false and explain what you found.
- Paths are relative to the repository root.

{CATEGORY_GUIDE}"""


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "strict": True,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


_PATH = {"type": "string", "description": "Path relative to the repository root."}
TOOLS = [
    _tool(
        "list_files",
        "List files under a directory, recursively (up to 200 entries).",
        {"path": {"type": "string", "description": "Directory, for example '.' or 'src'."}},
        ["path"],
    ),
    _tool("read_file", "Read a text file.", {"path": _PATH}, ["path"]),
    _tool(
        "edit_file",
        "Replace exactly one occurrence of old_str with new_str. old_str must match the file "
        "exactly, including whitespace, and must be unique. To create a file, pass an empty "
        "old_str and the full contents as new_str.",
        {"path": _PATH, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
        ["path", "old_str", "new_str"],
    ),
    _tool(
        "run_test",
        "Run the flaky test the given number of times (1-30), each in a fresh process. "
        "Returns how many runs failed and the output of the last failure.",
        {"runs": {"type": "integer"}},
        ["runs"],
    ),
    _tool(
        "submit_fix",
        "Finish. The harness then reruns the test 100 times to verify your fix.",
        {
            "fixed": {"type": "boolean", "description": "False if you couldn't fix it."},
            "category": {"type": "string", "enum": CATEGORIES},
            "explanation": {
                "type": "string",
                "description": "Markdown for the pull request: root cause, then the fix.",
            },
        },
        ["fixed", "category", "explanation"],
    ),
]


class AgentError(RuntimeError):
    pass


class ToolError(Exception):
    pass


@dataclass
class Step:
    kind: str  # "thinking" | "text" | "tool"
    tool: str | None = None
    input: dict | None = None
    output: str | None = None
    is_error: bool = False
    duration_s: float | None = None


@dataclass
class AgentResult:
    submitted: bool = False
    fixed: bool = False
    category: str | None = None
    explanation: str | None = None
    original_files: dict[str, str] = field(default_factory=dict)
    changed_files: dict[str, str] = field(default_factory=dict)
    usage: Usage = field(default_factory=Usage)
    model: str | None = None


class FixAgent:
    def __init__(
        self,
        client: Any,
        settings: Settings,
        sandbox: Sandbox,
        on_step: Callable[[Step], None] | None = None,
    ) -> None:
        self._client = client
        self._settings = settings
        self._sandbox = sandbox
        self._on_step = on_step or (lambda step: None)

    def run(self, workspace: Path, location: TestLocation, context: str) -> AgentResult:
        self._root = workspace.resolve()
        self._location = location
        self._result = AgentResult()
        messages: list[dict] = [{"role": "user", "content": _task(context)}]

        for _ in range(self._settings.agent_max_turns):
            response = self._client.beta.messages.create(
                **request_kwargs(self._settings),
                max_tokens=16000,
                system=SYSTEM,
                tools=TOOLS,
                output_config={"effort": self._settings.ai_effort},
                cache_control={"type": "ephemeral"},  # the history is resent every turn
                messages=messages,
            )
            self._result.usage.add(response.model, response.usage)
            self._result.model = response.model
            if response.stop_reason == "refusal":
                raise RefusalError("The model declined to continue.")

            for block in response.content:
                if block.type == "thinking" and block.thinking:
                    self._on_step(Step(kind="thinking", output=block.thinking))
                elif block.type == "text" and block.text.strip():
                    self._on_step(Step(kind="text", output=block.text))

            messages.append({"role": "assistant", "content": response.content})
            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                break
            if response.stop_reason == "max_tokens":
                raise AgentError("A tool call was cut off by max_tokens.")

            results = [self._call(block) for block in tool_uses]
            messages.append({"role": "user", "content": results})
            if self._result.submitted:
                break
        return self._result

    def _call(self, block: Any) -> dict:
        started = time.monotonic()
        try:
            output, is_error = self._execute(block.name, block.input), False
        except ToolError as exc:
            output, is_error = f"Error: {exc}", True
        self._on_step(
            Step(
                kind="tool",
                tool=block.name,
                input=block.input,
                output=output,
                is_error=is_error,
                duration_s=time.monotonic() - started,
            )
        )
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": output,
            "is_error": is_error,
        }

    def _execute(self, name: str, args: Any) -> str:
        if not isinstance(args, dict):
            raise ToolError("tool input must be an object")
        match name:
            case "list_files":
                return self._list_files(_str(args, "path"))
            case "read_file":
                path = self._resolve(_str(args, "path"))
                if not path.is_file():
                    raise ToolError("file not found")
                return path.read_text(encoding="utf-8", errors="replace")[:MAX_READ_CHARS]
            case "edit_file":
                return self._edit(_str(args, "path"), _str(args, "old_str"), _str(args, "new_str"))
            case "run_test":
                runs = args.get("runs")
                if not isinstance(runs, int):
                    raise ToolError("runs must be an integer")
                stats = self._sandbox.run_test(
                    self._root, self._location.node_id, max(1, min(runs, MAX_AGENT_RUNS))
                )
                text = f"{stats.failures} of {stats.runs} runs failed."
                if stats.last_failure:
                    text += f"\n\nLast failure:\n{stats.last_failure}"
                return text
            case "submit_fix":
                self._result.submitted = True
                self._result.fixed = bool(args.get("fixed"))
                self._result.category = args.get("category")
                self._result.explanation = args.get("explanation")
                return "Submitted. The harness will verify the fix."
        raise ToolError(f"unknown tool {name}")

    def _resolve(self, relative: str) -> Path:
        # Paths are model output: confine them to the checkout.
        target = (self._root / relative).resolve()
        if not target.is_relative_to(self._root):
            raise ToolError("path is outside the repository")
        return target

    def _list_files(self, relative: str) -> str:
        directory = self._resolve(relative)
        if not directory.is_dir():
            raise ToolError("directory not found")
        files = []
        for path in sorted(directory.rglob("*")):
            rel = path.relative_to(self._root)
            if path.is_file() and not SKIP_DIRS.intersection(rel.parts):
                files.append(rel.as_posix())
                if len(files) == MAX_LISTED_FILES:
                    files.append("... (truncated)")
                    break
        return "\n".join(files) or "(no files)"

    def _edit(self, relative: str, old: str, new: str) -> str:
        path = self._resolve(relative)
        key = path.relative_to(self._root).as_posix()
        current = path.read_text(encoding="utf-8") if path.is_file() else None
        if old == "":
            if current is not None:
                raise ToolError("file exists; pass the text to replace as old_str")
            updated = new
        else:
            if current is None:
                raise ToolError("file not found")
            count = current.count(old)
            if count != 1:
                raise ToolError(f"old_str must appear exactly once; found {count} matches")
            updated = current.replace(old, new, 1)
        self._result.original_files.setdefault(key, current or "")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
        self._result.changed_files[key] = updated
        return f"Edited {key}."


def _str(args: dict, key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str):
        raise ToolError(f"{key} must be a string")
    return value


def _task(context: str) -> str:
    return (
        f"{context}\n\n## Your task\n\nMake this test reliable. Reproduce the flake with "
        "run_test, find the root cause, fix it, confirm with run_test (at least 20 runs), "
        "then call submit_fix."
    )

import pytest

from flakehunter.agent import AgentError, FixAgent
from flakehunter.config import Settings
from flakehunter.llm import RefusalError
from flakehunter.testloc import locate_test
from tests.fakes import FakeClient, FakeSandbox, make_repo, message, text, thinking, tool_use

FIX = "def test_ready():\n    assert ready()  # FIXED\n"


@pytest.fixture
def setup(tmp_path):
    repo = make_repo(tmp_path / "repo")
    llm, sandbox, steps = FakeClient(), FakeSandbox(), []
    agent = FixAgent(llm, Settings(_env_file=None), sandbox, on_step=steps.append)
    location = locate_test(repo, "tests.test_clock::test_ready")
    return repo, llm, sandbox, steps, agent, location


def test_reproduce_edit_verify_submit(setup):
    repo, llm, sandbox, steps, agent, location = setup
    llm.messages.responses = [
        message(thinking("Let me reproduce it."), tool_use("run_test", runs=10)),
        message(tool_use("read_file", path="tests/test_clock.py")),
        message(
            tool_use(
                "edit_file",
                path="tests/test_clock.py",
                old_str="def test_ready():\n    assert ready()\n",
                new_str=FIX,
            )
        ),
        message(tool_use("run_test", runs=20)),
        message(
            text("Fixed."),
            tool_use("submit_fix", fixed=True, category="randomness", explanation="Seeded."),
        ),
    ]
    result = agent.run(repo, location, "context")

    assert result.submitted and result.fixed
    assert result.category == "randomness"
    assert result.changed_files["tests/test_clock.py"].endswith(FIX)
    assert "def test_ready():\n    assert ready()\n" in result.original_files["tests/test_clock.py"]
    assert sandbox.calls == [
        ("tests/test_clock.py::test_ready", 10),
        ("tests/test_clock.py::test_ready", 20),
    ]
    assert result.usage.cost_usd > 0

    tool_steps = [s for s in steps if s.kind == "tool"]
    assert [s.tool for s in tool_steps] == [
        "run_test", "read_file", "edit_file", "run_test", "submit_fix",
    ]  # fmt: skip
    assert tool_steps[0].output.startswith("5 of 10 runs failed")
    assert tool_steps[3].output.startswith("0 of 20 runs failed")
    assert steps[0].kind == "thinking"

    request = llm.messages.requests[-1]
    assert request["model"] == "claude-opus-5-5"
    assert request["fallbacks"] == "default"
    # The task, then an assistant turn and a tool-result turn for each of the 5 responses.
    roles = [m["role"] for m in request["messages"]]
    assert roles == ["user"] + ["assistant", "user"] * 5


def test_tool_errors_are_returned_to_the_model(setup):
    repo, llm, _, steps, agent, location = setup
    llm.messages.responses = [
        message(tool_use("read_file", path="../../etc/passwd")),
        message(tool_use("edit_file", path="tests/test_clock.py", old_str="nope", new_str="x")),
        message(text("I give up."), stop_reason="end_turn"),
    ]
    result = agent.run(repo, location, "context")

    assert not result.submitted
    errors = [s for s in steps if s.is_error]
    assert "outside the repository" in errors[0].output
    assert "found 0 matches" in errors[1].output
    assert result.changed_files == {}


def test_refusal_stops_the_agent(setup):
    repo, llm, _, _, agent, location = setup
    llm.messages.responses = [message(stop_reason="refusal")]
    with pytest.raises(RefusalError):
        agent.run(repo, location, "context")


def test_truncated_tool_call_is_not_executed(setup):
    repo, llm, sandbox, _, agent, location = setup
    llm.messages.responses = [message(tool_use("run_test", runs=5), stop_reason="max_tokens")]
    with pytest.raises(AgentError):
        agent.run(repo, location, "context")
    assert sandbox.calls == []

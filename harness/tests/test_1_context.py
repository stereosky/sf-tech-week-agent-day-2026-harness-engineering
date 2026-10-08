from harness.context import project
from harness.session import MemorySession


def chat_session() -> MemorySession:
    session = MemorySession()
    session.append("system/prompt", content="You are a test.")
    for turn, (question, reply) in enumerate([("I'm Tun", "Hi Tun"), ("I work on Kafka", "Nice")], start=1):
        session.turn, session.step = turn, 0
        session.append("user/message", content=question)
        session.step = 1
        session.append("assistant/message", content=reply)
        session.append("loop/exit", reason="stop on text")
    session.turn, session.step = 3, 0
    session.append("user/message", content="What do you know about me?")
    return session


def tool_session(steps: int) -> MemorySession:
    session = MemorySession()
    session.append("system/prompt", content="You are a test.")
    session.turn = 1
    session.append("user/message", content="Find the bad payment")
    for step in range(1, steps + 1):
        session.step = step
        call = {"name": "execute_sql", "arguments": {"sql": "SELECT 1"}}
        session.append("assistant/tool_call", content="", calls=[call])
        session.append("tool/result", name="execute_sql", content=f"result of step {step} " + "x" * 200)
    return session


def contents(window: list[dict]) -> str:
    return "\n".join(message["content"] for message in window)


def test_the_window_remembers_earlier_turns():
    window = project(chat_session().events(), budget=4000)
    assert "I'm Tun" in contents(window)
    assert "I work on Kafka" in contents(window)
    assert window[0]["role"] == "system"
    assert window[-1]["content"] == "What do you know about me?"


def test_project_is_a_pure_function():
    events = chat_session().events()
    assert project(events, budget=4000) == project(events, budget=4000)


def test_log_only_events_never_reach_the_model():
    session = chat_session()
    session.append("verifier/result", passed=True, reason="looked fine")
    text = contents(project(session.events(), budget=4000))
    assert "stop on text" not in text
    assert "looked fine" not in text


def test_old_tool_results_become_stubs_that_point_at_the_log():
    window = project(tool_session(steps=4).events(), budget=4000)
    tool_messages = [m["content"] for m in window if m["role"] == "tool"]
    assert len(tool_messages) == 4
    assert tool_messages[0].startswith("[") and "offset" in tool_messages[0]
    assert tool_messages[-1].startswith("result of step 4")


def test_a_tight_budget_keeps_the_goal_and_the_newest_step():
    window = project(tool_session(steps=6).events(), budget=150)
    text = contents(window)
    assert "Find the bad payment" in text
    assert "result of step 6" in text
    assert "step 1" not in text

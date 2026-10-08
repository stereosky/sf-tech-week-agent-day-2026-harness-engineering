import pytest

from harness import loop, settings
from harness.model import Reply
from harness.session import MemorySession
from harness.tools import Registry, Tool

LIST_TOPICS = Reply("", [{"name": "list_topics", "arguments": {"name_filter": ""}}], 10, 5)
ANSWER = Reply("ord_c2 has a negative amount", [], 10, 5)


@pytest.fixture
def session() -> MemorySession:
    session = MemorySession()
    session.append("system/prompt", content="You are a test.")
    session.turn = 1
    session.append("user/message", content="Find the bad payment")
    return session


@pytest.fixture
def registry() -> Registry:
    return Registry([Tool("list_topics", "", {"type": "object", "required": ["name_filter"]}, lambda _: "payments")])


def script(monkeypatch, *replies: Reply) -> None:
    queue = list(replies)
    monkeypatch.setattr(loop.model, "chat", lambda messages, tools: queue.pop(0) if len(queue) > 1 else queue[0])


def test_the_loop_runs_until_the_model_answers(monkeypatch, session, registry):
    script(monkeypatch, LIST_TOPICS, ANSWER)
    assert loop.run_turn(session, registry) == "ord_c2 has a negative amount"
    kinds = [e["type"] for e in session.events()]
    assert kinds.count("tool/result") == 1
    assert kinds[-1] == "loop/exit"
    assert session.events()[-1]["data"]["reason"] == "stop on text"


def test_caps_stop_a_model_that_never_answers(monkeypatch, session, registry):
    script(monkeypatch, LIST_TOPICS)
    answer = loop.run_turn(session, registry)
    assert "max steps" in answer
    assert session.step == settings.MAX_STEPS

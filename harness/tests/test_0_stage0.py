import json

from harness import model, settings, stage0, turn
from harness.session import MemorySession

INVENTED = json.dumps({"order_id": "12345", "what_is_wrong": "The amount field contains non-numeric data."})


def fake_ollama(monkeypatch):
    """Ollama's /api/chat as stage 0 calls it. Returns the request bodies it was sent."""
    sent = []

    def post(body):
        sent.append(body)
        reply = {"message": {"content": INVENTED}, "prompt_eval_count": 300, "eval_count": 30}
        return type("Response", (), {"status_code": 200, "text": "", "json": lambda self: reply})()

    monkeypatch.setattr(model, "_post", post)
    return sent


def started_session() -> MemorySession:
    session = MemorySession()
    session.turn = 1
    session.append("system/prompt", content="system")
    session.append("user/message", content=settings.TASK_PROMPT)
    return session


def test_the_harness_demands_an_order_id_and_offers_no_tools(monkeypatch):
    sent = fake_ollama(monkeypatch)
    stage0.ask(started_session())
    assert "tools" not in sent[0]
    assert sent[0]["format"]["required"] == ["order_id", "what_is_wrong"]
    assert sent[0]["format"]["properties"]["order_id"]["minLength"] == 1  # an empty string is not a way out


def test_the_forced_answer_lands_on_the_session_and_says_so(monkeypatch):
    fake_ollama(monkeypatch)
    session = started_session()
    forced = stage0.ask(session)
    assert forced.answer == INVENTED
    assert "STAGE0_JSON" in forced.label and settings.MODEL in forced.label
    answers = [e for e in session.events() if e["type"] == "assistant/message"]
    assert answers[0]["data"]["content"] == INVENTED and answers[0]["data"]["answer_format"] == "stage0"
    assert session.tokens == 330


def test_switching_stage0_off_runs_the_normal_loop(monkeypatch):
    monkeypatch.setattr(settings, "STAGE0_JSON", False)
    assert stage0.ask(started_session()) is None


def test_other_questions_are_never_forced_into_the_schema():
    assert not turn.is_investigation("Hi, I'm Tun")

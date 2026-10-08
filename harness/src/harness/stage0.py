"""Stage 0: before any tools, the harness demands an answer the model has no way to know.

Asked in plain text, qwen3.5:2b says it can't see the cluster. But harnesses
often require structured output and Ollama's `format` constrains decoding to a
JSON schema. When the schema requires an order_id, "I can't see it" is no
longer a reply the model can produce, so it makes one up: a different ID on
almost every run and none of them on the payments topic. Set STAGE0_JSON =
False in settings.py to let it answer in plain text instead.
"""

from dataclasses import dataclass

from harness import model, settings
from harness.context import project

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {
        "order_id": {"type": "string", "minLength": 1},
        "what_is_wrong": {"type": "string", "minLength": 1},
    },
    "required": ["order_id", "what_is_wrong"],
}


@dataclass
class Stage0:
    answer: str
    label: str


def ask(session) -> Stage0 | None:
    """One live model call that must fill in ANSWER_SCHEMA. None means: run the normal loop."""
    if not settings.STAGE0_JSON:
        return None
    session.step += 1
    events = session.events()
    window = project(events, settings.WINDOW_BUDGET)
    reply = model.chat(window, [], answer_format=ANSWER_SCHEMA)
    session.tokens += reply.prompt_tokens + reply.completion_tokens
    session.say("[stage 0] no tools on the menu and the harness requires JSON with an order_id")
    session.say(f"[step {session.step}] window: {len(window)} messages, {reply.prompt_tokens} prompt tokens")
    seen = {"context_upto": events[-1]["offset"], "prompt_tokens": reply.prompt_tokens}
    session.append("assistant/message", content=reply.content, answer_format="stage0", **seen)
    session.append("loop/exit", reason="stage 0: one forced JSON answer")
    label = (
        f"Stage 0: {settings.MODEL} had no tools and the harness required a JSON answer with an order_id, "
        "so it had to write one. Set STAGE0_JSON = False in settings.py to let it answer in plain text."
    )
    return Stage0(reply.content, label)

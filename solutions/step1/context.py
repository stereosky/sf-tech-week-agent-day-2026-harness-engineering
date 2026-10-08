"""1 · Context manager: the model only sees the window you assemble.

The session log is an append-only Kafka topic (see session.py). Before every
model call the harness reads the session back and folds it into a window with
project(). The log keeps every byte; the window is a view you can rebuild.
"""

import json

from harness import settings

SYSTEM_PROMPT = (
    "You are an investigator for a Kafka cluster. You can only act through the tools the harness registered.\n"
    "Answer briefly and plainly."
)

SURFACE = {
    "user/message",
    "assistant/tool_call",
    "tool/result",
    "guardrail/block",
    "assistant/message",
    "verifier/result",
}


def assemble_system_prompt() -> str:
    """The system prompt plus the FILES box. Same bytes every call, so Ollama can reuse its prompt cache."""
    agents_md = (settings.FILES_DIR / "AGENTS.md").read_text()
    return f"{SYSTEM_PROMPT}\n\n# AGENTS.md\n\n{agents_md}"


def project(events: list[dict], budget: int) -> list[dict]:
    """Pure fold over the session log: same events and budget in, same window out."""
    system = render(first(events, "system/prompt"))
    history = [event for event in events if on_surface(event)]
    return [system] + fit(history, budget - estimate_tokens([system]))


def on_surface(event: dict) -> bool:
    """Log-only events (loop/exit, verifier passes) are for humans and never reach the model."""
    if event["type"] == "verifier/result":
        return event["data"]["passed"] is False
    return event["type"] in SURFACE


def fit(events: list[dict], budget: int) -> list[dict]:
    """Newest steps first until the budget runs out. The goal and the newest question always stay.

    Tool results older than KEEP_VERBATIM_STEPS become stubs that point at their Kafka offset.
    """
    pinned = {e["offset"]: e for e in (first(events, "user/message"), last(events, "user/message")) if e}
    chosen = {offset: render(event) for offset, event in pinned.items()}
    used = estimate_tokens(list(chosen.values()))
    groups = steps([event for event in events if event["offset"] not in pinned])
    for age, group in enumerate(reversed(groups)):
        rendered = {e["offset"]: render(e, stub=age >= settings.KEEP_VERBATIM_STEPS) for e in group}
        cost = estimate_tokens(list(rendered.values()))
        if age > 0 and used + cost > budget:
            break  # the newest step always goes in, even over budget
        chosen.update(rendered)
        used += cost
    return [chosen[offset] for offset in sorted(chosen)]


def render(event: dict, stub: bool = False) -> dict:
    """One event as one chat message in Ollama's format."""
    kind, data = event["type"], event["data"]
    if kind in ("system/prompt", "user/message", "assistant/message"):
        return {"role": kind.split("/")[0], "content": data["content"]}
    if kind == "assistant/tool_call":
        calls = [{"function": {"name": c["name"], "arguments": c["arguments"]}} for c in data["calls"]]
        return {"role": "assistant", "content": data.get("content", ""), "tool_calls": calls}
    if kind == "verifier/result":
        feedback = f"The harness checked your answer against Kafka: {data['reason']}. Try again."
        return {"role": "user", "content": feedback}
    content = data["content"] if kind == "tool/result" else f"BLOCKED by a guardrail: {data['reason']}"
    if stub and kind == "tool/result":
        where = f"{settings.SESSION_TOPIC} offset {event['offset']}"
        content = f"[{len(content)} chars elided by the context manager: {where}]"
    return {"role": "tool", "tool_name": data["name"], "content": content}


def steps(events: list[dict]) -> list[list[dict]]:
    """Group events by (turn, step), oldest first, so a tool call and its results stay together."""
    groups: dict[tuple, list[dict]] = {}
    for event in events:
        groups.setdefault((event["turn"], event["step"]), []).append(event)
    return list(groups.values())


def estimate_tokens(items: list[dict]) -> int:
    """About 3 characters per token for Qwen on JSON. Ollama reports the real count as prompt_eval_count."""
    return sum(len(json.dumps(item)) // 3 + 4 for item in items)


def first(events: list[dict], kind: str) -> dict | None:
    return next((event for event in events if event["type"] == kind), None)


def last(events: list[dict], kind: str) -> dict | None:
    return next((event for event in reversed(events) if event["type"] == kind), None)

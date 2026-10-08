"""4 · Loop: a step is one model request plus its tools.

Nothing happens until something calls the window, the model, the gate and the
tools in order. That something is a while loop and deciding when it stops is
harness work.
"""

import json

from harness import model, settings
from harness.context import estimate_tokens, project
from harness.guardrails import check_caps, check_tool


def step(session, registry) -> model.Reply:
    """One model request plus the tools it asked for."""
    session.step += 1
    events = session.events()
    tools = registry.schemas()
    window = project(events, settings.WINDOW_BUDGET - estimate_tokens(tools))
    reply = model.chat(window, tools)
    session.tokens += reply.prompt_tokens + reply.completion_tokens
    seen = {"context_upto": events[-1]["offset"], "prompt_tokens": reply.prompt_tokens}
    session.say(f"[step {session.step}] window: {len(window)} messages, {reply.prompt_tokens} prompt tokens")

    if not reply.tool_calls:
        session.append("assistant/message", content=reply.content, **seen)
        return reply

    session.append("assistant/tool_call", content=reply.content, calls=reply.tool_calls, **seen)
    for call in reply.tool_calls:
        name, arguments = call["name"], call["arguments"]
        session.say(f"  → {name}({json.dumps(arguments)})")
        decision = check_tool(name, arguments)
        if decision.blocked:
            session.append("guardrail/block", name=name, arguments=arguments, reason=decision.reason)
            session.say(f"  ✗ GUARDRAIL {decision.reason}")
            continue
        result = registry.run(name, arguments)
        session.append("tool/result", name=name, content=result)
        session.say(f"    {preview(result)}")
    return reply


def run_turn(session, registry) -> str:
    """Starter: exactly one step, then stop."""
    # TODO(4): repeat steps until the model answers in text. Check check_caps() before every step.
    reply = step(session, registry)
    if reply.tool_calls:
        session.append("loop/exit", reason="one step only")
        return no_loop_yet(session)
    session.append("loop/exit", reason="stop on text")
    return reply.content


def no_loop_yet(session) -> str:
    """What the starter harness shows after its single step: raw results that nothing reads."""
    results = [
        e for e in session.events() if e["turn"] == session.turn and e["type"] in ("tool/result", "guardrail/block")
    ]
    shown = "\n\n".join(
        f"{e['data']['name']}:\n{e['data'].get('content') or 'BLOCKED: ' + e['data']['reason']}" for e in results
    )
    note = "The model asked for tools and the harness ran them. There is no loop yet, so nothing reads the results."
    return f"{note}\n\n{shown}"


def preview(text: str, width: int = 110) -> str:
    first_line = text.strip().splitlines()[0] if text.strip() else "(empty)"
    more = len(text.strip().splitlines()) - 1
    line = first_line if len(first_line) <= width else first_line[: width - 3] + "..."
    return f"{line}  (+{more} more lines)" if more > 0 else line

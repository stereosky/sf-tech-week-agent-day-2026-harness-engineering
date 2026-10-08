"""An OpenAI-compatible endpoint, so OpenCode can use the harness as if it were a model.

OpenCode sends its own system prompt and the whole transcript on every request.
The harness keeps only the newest user message and the session id: the window
the model sees is rebuilt from Kafka, never taken from the client.
"""

import asyncio
import hashlib
import html
import json
import threading
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

from harness import oauth, settings, turn
from harness.session import Session

MODEL_ID = "harness-agent"
KEEPALIVE_SECONDS = 5

app = FastAPI(title="Let's Build an Agent Harness")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "model": settings.MODEL}


@app.get("/v1/models")
def models() -> dict:
    return {"object": "list", "data": [{"id": MODEL_ID, "object": "model", "owned_by": "you"}]}


@app.get("/login")
def login():
    """Step 1 of the Lenses login: off to HQ, where you sign in and grant the read scope."""
    return RedirectResponse(oauth.start_login())


@app.get("/oauth/callback")
def oauth_callback(code: str = "", state: str = "", error: str = ""):
    """Step 2: HQ sends your browser back here with a code and the harness swaps it for tokens."""
    try:
        if error:
            raise oauth.LoginRequired(f"Lenses answered {error}")
        stored = oauth.finish_login(code, state)
    except oauth.LoginRequired as exc:
        return HTMLResponse(page(str(exc)), status_code=400)
    return HTMLResponse(page(f"The harness is logged into Lenses with the {stored['scope']} scope. Back to OpenCode."))


def page(message: str) -> str:
    return f"<!doctype html><title>Agent harness</title><p style='font:1.2em system-ui'>{html.escape(message)}</p>"


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    body = await request.json()
    messages = body.get("messages") or []
    session_id = session_id_for(request, body, messages)
    questions = [text_of(m) for m in messages if m.get("role") == "user"]
    question, turn_no = (questions[-1] if questions else ""), len(questions)
    if body.get("stream"):
        return StreamingResponse(stream(session_id, question, turn_no), media_type="text/event-stream")

    trace: list[str] = []
    outcome = await asyncio.to_thread(turn.handle, Session(session_id, trace.append), question, turn_no)
    return JSONResponse(completion(outcome, "\n".join(trace)))


def session_id_for(request: Request, body: dict, messages: list[dict]) -> str:
    """OpenCode sends its session id as a header. Fall back to the body, then to the first message."""
    for header in ("x-session-id", "x-session-affinity"):
        if value := request.headers.get(header):
            return value
    if value := body.get("promptCacheKey") or body.get("prompt_cache_key"):
        return value
    first = next((text_of(m) for m in messages if m.get("role") == "user"), "")
    return "anon-" + hashlib.sha256(first.encode()).hexdigest()[:12]


def text_of(message: dict) -> str:
    content = message.get("content") or ""
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return str(content)


async def stream(session_id: str, question: str, turn_no: int):
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def say(line: str) -> None:
        print(f"[{session_id[-8:]}] {line}", flush=True)
        loop.call_soon_threadsafe(queue.put_nowait, ("trace", line))

    def work() -> None:
        try:
            outcome = turn.handle(Session(session_id, say), question, turn_no)
            loop.call_soon_threadsafe(queue.put_nowait, ("done", outcome))
        except Exception as exc:  # the chat window is the only place a participant will look
            loop.call_soon_threadsafe(queue.put_nowait, ("error", f"{type(exc).__name__}: {exc}"))

    threading.Thread(target=work, daemon=True).start()
    completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    yield chunk(completion_id, {"role": "assistant", "content": ""})
    while True:
        try:
            kind, item = await asyncio.wait_for(queue.get(), timeout=KEEPALIVE_SECONDS)
        except TimeoutError:
            yield chunk(completion_id, {"content": ""})  # keeps OpenCode's chunk timeout from firing
            continue
        if kind == "trace":
            yield chunk(completion_id, {"reasoning_content": item + "\n"})
            continue
        text = item.report() if kind == "done" else f"Harness error: {item}"
        tokens = item.tokens if kind == "done" else 0
        yield chunk(completion_id, {"content": text})
        yield chunk(completion_id, {}, finish_reason="stop")
        yield sse(
            {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "model": MODEL_ID,
                "choices": [],
                "usage": {"prompt_tokens": tokens, "completion_tokens": 0, "total_tokens": tokens},
            }
        )
        yield "data: [DONE]\n\n"
        return


def chunk(completion_id: str, delta: dict, finish_reason: str | None = None) -> str:
    return sse(
        {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": MODEL_ID,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
        }
    )


def sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


def completion(outcome: turn.Outcome, trace: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": MODEL_ID,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": outcome.report(), "reasoning_content": trace},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": outcome.tokens, "completion_tokens": 0, "total_tokens": outcome.tokens},
    }

"""The only module that talks to the model: Ollama's native /api/chat.

The native API (not the OpenAI-compatible /v1) is what lets the harness own the
window: it accepts num_ctx per request, can switch thinking off and can refuse
to truncate. Swap this file to change model provider; nothing else knows the
wire format.
"""

import json
from dataclasses import dataclass, field

import httpx

from harness import settings


class ModelError(RuntimeError):
    pass


@dataclass
class Reply:
    content: str
    tool_calls: list[dict] = field(default_factory=list)  # [{"name": str, "arguments": dict}]
    prompt_tokens: int = 0
    completion_tokens: int = 0


def chat(messages: list[dict], tools: list[dict], answer_format: dict | None = None) -> Reply:
    """One model request. The harness decides everything the model sees; Ollama decides nothing.

    answer_format: a JSON schema the reply must match. Ollama constrains decoding to it.
    """
    body = {
        "model": settings.MODEL,
        "messages": messages,
        "stream": False,
        "think": False,  # thinking is slow on a laptop, eats the window and loops on small Qwen3.5 models
        "truncate": False,  # an oversized window is an error, never a silent cut of the oldest messages
        "shift": False,
        "options": {
            "num_ctx": settings.NUM_CTX,
            "num_predict": settings.NUM_PREDICT,
            "temperature": settings.TEMPERATURE,
            "top_p": settings.TOP_P,
            "top_k": settings.TOP_K,
        },
    }
    if tools:
        body["tools"] = tools
    if answer_format:
        body["format"] = answer_format
    response = _post(body)
    if response.status_code == 400 and "does not support thinking" in response.text:
        body.pop("think")
        response = _post(body)
    if response.status_code != 200:
        raise ModelError(f"Ollama answered {response.status_code}: {response.text[:400]}")

    data = response.json()
    message = data.get("message") or {}
    content = message.get("content") or ""
    calls = [
        {"name": call["function"]["name"], "arguments": _arguments(call["function"].get("arguments"))}
        for call in message.get("tool_calls") or []
    ]
    if not calls and tools:
        calls = tool_calls_in_text(content, {tool["function"]["name"] for tool in tools})
        if calls:
            content = ""
    return Reply(content.strip(), calls, data.get("prompt_eval_count", 0), data.get("eval_count", 0))


def _post(body: dict) -> httpx.Response:
    try:
        return httpx.post(f"{settings.OLLAMA_URL}/api/chat", json=body, timeout=600)
    except httpx.HTTPError as exc:
        raise ModelError(f"cannot reach Ollama at {settings.OLLAMA_URL}: {exc}") from exc


def _arguments(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def tool_calls_in_text(text: str, names: set[str]) -> list[dict]:
    """Small models sometimes write a tool call as JSON in the reply instead of calling it.

    Accept it only if it names a tool that is on the menu.
    """
    decoder, calls, position = json.JSONDecoder(), [], 0
    while (position := text.find("{", position)) != -1:
        try:
            candidate, end = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            position += 1
            continue
        if isinstance(candidate, dict) and candidate.get("name") in names:
            arguments = candidate.get("arguments", candidate.get("parameters"))
            calls.append({"name": candidate["name"], "arguments": _arguments(arguments)})
        position = end
    return calls

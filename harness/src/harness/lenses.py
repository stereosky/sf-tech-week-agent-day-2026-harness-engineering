"""Lenses MCP: a client, plus the way the harness presents Lenses tools to a small model.

The MCP server ships about 45 tools, all of which need an `environment` argument,
and shows a read-scoped token the 24 that only read. The harness narrows that
down further: it fills in the environment itself, gives every tool a required
parameter (Ollama skips tool calls with no arguments) and turns big JSON
responses into a few lines a 2B model can read.
"""

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from harness import oauth, settings


class LensesError(RuntimeError):
    pass


async def _with_session(action):
    """Every request carries the token from your login, so Lenses sees you and the scope you granted."""
    headers = {"Authorization": f"Bearer {oauth.access_token()}"}
    async with create_mcp_http_client(headers=headers) as http:
        async with streamable_http_client(settings.LENSES_MCP_URL, http_client=http) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await action(session)


def call(name: str, arguments: dict) -> Any:
    """Call one MCP tool and return its result as Python data."""
    try:
        result = asyncio.run(_with_session(lambda session: session.call_tool(name, arguments)))
    except oauth.LoginRequired:
        raise
    except Exception as exc:
        raise LensesError(f"cannot call Lenses MCP at {settings.LENSES_MCP_URL}: {exc}") from exc
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    if result.is_error:
        raise LensesError(" ".join(texts) or f"{name} failed")
    structured = result.structured_content
    if structured is not None:
        return structured["result"] if isinstance(structured, dict) and set(structured) == {"result"} else structured
    try:
        return json.loads(texts[0]) if len(texts) == 1 else [json.loads(text) for text in texts]
    except json.JSONDecodeError:
        return "\n".join(texts)


def list_tools() -> list:
    try:
        return asyncio.run(_with_session(lambda session: session.list_tools())).tools
    except oauth.LoginRequired:
        raise
    except Exception as exc:
        raise LensesError(f"cannot list Lenses MCP tools at {settings.LENSES_MCP_URL}: {exc}") from exc


def call_raw(name: str, arguments: dict, schema: dict) -> str:
    """For REGISTER_ALL_MCP_TOOLS: the tool exactly as the server describes it, environment filled in."""
    if "environment" in schema.get("properties", {}):
        arguments = {**arguments, "environment": settings.LENSES_ENVIRONMENT}
    return json.dumps(call(name, arguments), default=str)


def shape_topics(topics: list[dict], name_filter: str) -> str:
    visible = [
        topic
        for topic in topics
        if not topic.get("isControlTopic")
        and not topic.get("topicName", "_").startswith("_")
        and topic.get("topicName") != settings.SESSION_TOPIC
        and name_filter.lower() in topic.get("topicName", "").lower()
    ]
    if not visible:
        return f"No topics match {name_filter!r}. Use an empty name_filter to list every topic."
    return "\n".join(
        f"{t['topicName']}  ({t.get('totalMessages', '?')} messages, value format {t.get('valueType', '?')})"
        for t in visible
    )


def shape_rows(rows: list[dict]) -> str:
    if not rows:
        return (
            "0 rows. Lenses also returns 0 rows when the SQL is invalid or the topic does not exist, "
            "so check the topic name with list_topics."
        )
    lines = [f"key={row.get('key')} value={json.dumps(row.get('value'), sort_keys=True)}" for row in rows]
    values = [row["value"] for row in rows if isinstance(row.get("value"), dict)]
    fields = {field for value in values for field in value}
    always_null = sorted(f for f in fields if all(value.get(f) is None for value in values))
    if always_null:
        lines.append(
            f"Note: {', '.join(always_null)} is null in every row, so that field probably does not exist. "
            "SELECT * shows the real fields."
        )
    return "\n".join(lines)


def list_topics(arguments: dict) -> str:
    topics = call("list_topics", {"environment": settings.LENSES_ENVIRONMENT})
    return shape_topics(topics, arguments.get("name_filter", ""))


def execute_sql(arguments: dict) -> str:
    rows = call("execute_sql", {"environment": settings.LENSES_ENVIRONMENT, "sql": arguments["sql"]})
    return shape_rows(rows or [])


TOOLS = {
    "list_topics": {
        "description": "List the Kafka topics on this cluster with their message counts.",
        "parameters": {
            "type": "object",
            "properties": {
                "name_filter": {
                    "type": "string",
                    "description": "Part of a topic name to match. Use an empty string to list every topic.",
                }
            },
            "required": ["name_filter"],
        },
        "run": list_topics,
    },
    "execute_sql": {
        "description": "Run a Lenses SQL query against Kafka and return the matching records.",
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {"type": "string", "description": "Lenses SQL, for example: SELECT * FROM payments LIMIT 20"}
            },
            "required": ["sql"],
        },
        "run": execute_sql,
    },
}

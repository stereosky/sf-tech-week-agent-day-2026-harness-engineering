"""2 · Tool registry: the model can only act through tools you register.

A registry is a curated menu: the schemas the model sees plus the code the
harness runs. Every schema on the menu is sent with every model call, used or
not, so a small menu leaves more of the window for the work.
"""

from collections.abc import Callable
from dataclasses import dataclass

from harness import lenses, settings


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    run: Callable[[dict], str]

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }


class Registry:
    def __init__(self, tools: list[Tool]):
        self.tools = {tool.name: tool for tool in tools}

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self.tools.values()]

    def run(self, name: str, arguments: dict) -> str:
        """Errors come back as text the model can read and act on, never as a crash."""
        tool = self.tools.get(name)
        if tool is None:
            return f"error: there is no tool called {name!r}. The tools are: {', '.join(self.tools) or 'none'}"
        missing = [p for p in tool.parameters.get("required", []) if p not in arguments]
        if missing:
            return f"error: {name} needs {', '.join(missing)}"
        try:
            return truncate(str(tool.run(arguments)))
        except Exception as exc:
            return f"error: {name} failed: {exc}"


def read_file(arguments: dict) -> str:
    """A local tool the harness owns. It can only see the harness's own files."""
    root = settings.FILES_DIR.resolve()
    path = (root / arguments["path"]).resolve()
    if root not in path.parents or not path.is_file():
        return f"error: {arguments['path']} is not a file in the workspace. Try AGENTS.md"
    return path.read_text()


READ_FILE = Tool(
    "read_file",
    "Read a file from the workspace, for example AGENTS.md.",
    {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    read_file,
)


def lenses_tool(name: str) -> Tool:
    """A Lenses MCP tool, reshaped by the harness for a small model (see lenses.py)."""
    return Tool(name, **lenses.TOOLS[name])


def every_lenses_tool() -> list[Tool]:
    """All the MCP server's tools exactly as it describes them: the context tax, made visible."""

    def runner(tool):
        return lambda arguments: lenses.call_raw(tool.name, arguments, tool.input_schema)

    return [Tool(t.name, t.description or "", t.input_schema, runner(t)) for t in lenses.list_tools()]


def registry() -> Registry:
    """The menu for this turn. What is not on it does not exist to the model."""
    if settings.REGISTER_ALL_MCP_TOOLS:
        return Registry([READ_FILE, *every_lenses_tool()])
    return Registry(
        [
            # TODO(2): an empty menu. Add the local READ_FILE tool, then lenses_tool("list_topics")
            # and lenses_tool("execute_sql") from Lenses MCP.
        ]
    )


def truncate(text: str, limit: int = settings.MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    head, tail = text[: limit // 4], text[-(limit - limit // 4) :]
    return f"{head}\n... [{len(text) - limit} characters cut by the harness] ...\n{tail}"

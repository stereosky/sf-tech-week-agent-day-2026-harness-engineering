"""3 · Guardrails: decide whether this call may run.

Plain code between the model's request and the environment. It spends zero
tokens and the model gets no vote. Registered is not the same as permitted.
"""

from dataclasses import dataclass

from harness import settings


@dataclass
class Decision:
    allowed: bool
    reason: str = ""

    @property
    def blocked(self) -> bool:
        return not self.allowed

    @classmethod
    def allow(cls) -> "Decision":
        return cls(True)

    @classmethod
    def block(cls, reason: str) -> "Decision":
        return cls(False, reason)


def check_tool(name: str, arguments: dict) -> Decision:
    """Runs after the model asks for a tool and before anything touches Kafka."""
    if name == "execute_sql" and settings.SESSION_TOPIC in arguments.get("sql", ""):
        return Decision.block(f"{settings.SESSION_TOPIC} is the harness's own log and is off limits")
    if name == "execute_sql":
        sql = arguments.get("sql", "").strip().rstrip(";")
        words = sql.split()
        if ";" in sql or not words or words[0].upper() != "SELECT":
            return Decision.block("execute_sql allows a single SELECT only")
    return Decision.allow()


def check_caps(steps: int, tokens: int) -> Decision:
    """Caps on the whole turn. The loop checks them before every step."""
    if steps >= settings.MAX_STEPS:
        return Decision.block(f"max steps ({settings.MAX_STEPS}) reached")
    if tokens >= settings.RUN_TOKEN_BUDGET:
        return Decision.block(f"run token budget ({settings.RUN_TOKEN_BUDGET}) reached")
    return Decision.allow()

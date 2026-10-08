"""A session is one OpenCode conversation. Its events live on Kafka, keyed by the session id."""

import uuid
from collections.abc import Callable
from datetime import UTC, datetime

from harness import kafka_log, settings


class Session:
    def __init__(self, session_id: str, say: Callable[[str], None] = print):
        self.id = session_id
        self.say = say  # streams one line of trace to OpenCode
        self.turn = 0  # which user message this is
        self.step = 0  # model requests made so far in this turn
        self.tokens = 0  # prompt plus completion tokens spent in this turn

    def _event(self, kind: str, data: dict) -> dict:
        return {
            "event_id": uuid.uuid4().hex,
            "session_id": self.id,
            "turn": self.turn,
            "step": self.step,
            "type": kind,
            "ts": datetime.now(UTC).isoformat(),
            "data": data,
        }

    def append(self, kind: str, **data) -> dict:
        """Append one event to the log and return it with its Kafka offset."""
        event = self._event(kind, data)
        event["offset"] = kafka_log.append(settings.SESSION_TOPIC, self.id, event)
        return event

    def events(self) -> list[dict]:
        """The whole session, read back from Kafka in offset order."""
        rows = kafka_log.read(settings.SESSION_TOPIC, key=self.id)
        return [{**row["value"], "offset": row["offset"]} for row in rows]


class MemorySession(Session):
    """The same interface over a Python list. For tests: it forgets everything when the process exits."""

    def __init__(self, session_id: str = "test", say: Callable[[str], None] = lambda _: None):
        super().__init__(session_id, say)
        self._events: list[dict] = []

    def append(self, kind: str, **data) -> dict:
        event = {**self._event(kind, data), "offset": len(self._events)}
        self._events.append(event)
        return event

    def events(self) -> list[dict]:
        return list(self._events)

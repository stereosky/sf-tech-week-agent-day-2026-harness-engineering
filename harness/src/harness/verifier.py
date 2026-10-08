"""5 · Verifier: inspect the environment, not the model's claim.

The loop stopping says nothing about the answer being right. The verifier reads
Kafka through its own consumer (not the model, not the MCP path the agent used)
and decides from the data. Its feedback must never leak the answer.
"""

from dataclasses import dataclass


@dataclass
class Verdict:
    passed: bool | None  # None: nothing checked this answer
    reason: str

    @classmethod
    def ok(cls, reason: str) -> "Verdict":
        return cls(True, reason)

    @classmethod
    def fail(cls, reason: str) -> "Verdict":
        return cls(False, reason)

    @classmethod
    def skip(cls, reason: str) -> "Verdict":
        return cls(None, reason)


def verify(answer: str, payments: list[dict], offsets: tuple[int, int]) -> Verdict:
    """Check the answer to the /investigate task against what is on Kafka.

    payments: every record on the payments topic, read by the harness's own consumer
    offsets:  (payments end offset when the turn started, payments end offset now)
    """
    # TODO(5): find the invalid payment in `payments`, check it's the last payment the answer names
    # (an answer may list every record before its conclusion) and check nothing was written
    return Verdict.skip("TODO(5): nothing checks this answer yet, so you are trusting the model")

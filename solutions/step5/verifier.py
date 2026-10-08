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
    invalid = [p.get("order_id") for p in payments if isinstance(p.get("amount"), (int, float)) and p["amount"] < 0]
    named = [p["order_id"] for p in payments if p.get("order_id") and p["order_id"] in answer]
    concluded = max(named, key=answer.rfind, default=None)  # the payment the answer mentions last
    if len(invalid) != 1 or concluded != invalid[0]:  # an answer may list every record; its conclusion counts
        return Verdict.fail("the answer must conclude with one payment, the invalid one")
    if offsets[0] != offsets[1]:
        return Verdict.fail("the payments end offset moved, so a write reached the environment")
    return Verdict.ok(f"answer names {invalid[0]}; payments unchanged at {offsets[1]} records")

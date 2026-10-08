"""The harness owns the turn: record the question, run the loop, verify the answer, report."""

from dataclasses import dataclass

from harness import kafka_log, lenses, oauth, settings, stage0, tools
from harness.context import assemble_system_prompt
from harness.lenses import LensesError
from harness.loop import run_turn
from harness.model import ModelError
from harness.session import Session
from harness.verifier import Verdict, verify


@dataclass
class Outcome:
    answer: str
    verdict: Verdict | None
    tokens: int
    note: str = ""  # shown under the answer, e.g. that stage 0 forced the answer's shape

    def report(self) -> str:
        answer = self.answer or "(the model returned an empty reply)"
        shown = f"{answer}\n\n---\n" + (f"{self.note}\n" if self.note else "")
        if self.verdict is None:
            return f"{shown}Verify: no check registered for this question, so this is the model's word."
        label = {True: "✓ Verified", False: "✗ Verification failed", None: "Verify: skipped"}[self.verdict.passed]
        return f"{shown}{label}: {self.verdict.reason}"


def handle(session: Session, question: str, turn_no: int) -> Outcome:
    """One user message in, one answer out. Everything in between lands on the session log."""
    events = session.events()
    session.turn = turn_no
    if not events:
        session.append("system/prompt", content=assemble_system_prompt())
    asked = [e["data"]["content"] for e in events if e["type"] == "user/message"]
    if len(asked) < turn_no or asked[-1] != question:
        session.append("user/message", content=question)

    payments_at_start = kafka_log.end_offset(settings.PAYMENTS_TOPIC)
    forced = None
    try:
        registry = tools.registry()
        session.say(f"[turn {turn_no}] {len(registry.tools)} tools on the menu, model {settings.MODEL}")
        if any(name in lenses.TOOLS for name in registry.tools):
            oauth.access_token()  # no login: stop here with the link, before the model sees a tool error
        if not registry.tools and is_investigation(question):
            forced = stage0.ask(session)  # stage 0: an answer shape the model can only fill by inventing
        answer = forced.answer if forced else run_turn(session, registry)
        verdict = None
        if is_investigation(question):
            answer, verdict = verify_with_retries(session, registry, answer, payments_at_start)
    except (ModelError, LensesError, oauth.LoginRequired) as exc:
        session.append("loop/exit", reason=f"error: {exc}")
        answer, verdict = f"The harness stopped on an error: {exc}", None
    return Outcome(answer, verdict, session.tokens, forced.label if forced else "")


def is_investigation(question: str) -> bool:
    """The verifier has one registered check: the /investigate task."""
    return " ".join(settings.TASK_PROMPT.split()) in " ".join(question.split())


def verify_with_retries(session: Session, registry, answer: str, payments_at_start: int):
    for attempt in range(settings.MAX_VERIFY_RETRIES + 1):
        payments = [row["value"] for row in kafka_log.read(settings.PAYMENTS_TOPIC)]
        offsets = (payments_at_start, kafka_log.end_offset(settings.PAYMENTS_TOPIC))
        verdict = verify(answer, [p for p in payments if isinstance(p, dict)], offsets)
        if verdict.passed is None:
            session.say(f"[verify] skipped: {verdict.reason}")
            return answer, verdict
        session.append("verifier/result", passed=verdict.passed, reason=verdict.reason)
        session.say(f"[verify] {'PASS' if verdict.passed else 'FAIL'}: {verdict.reason}")
        if verdict.passed or attempt == settings.MAX_VERIFY_RETRIES:
            return answer, verdict
        session.say("[verify] sending the failure back to the loop")
        answer = run_turn(session, registry)
    return answer, verdict

"""You can optionally run these inside the harness container to check the differences in output on many runs.

    python -m harness.rehearse ask "Hi, I'm Tun" "What is my name?"   one session, one turn per question
    python -m harness.rehearse bakeoff --runs 10 --model qwen3.5:2b  the /investigate task N times
    python -m harness.rehearse stage0 --runs 5                       the stage-0 answer N times, no tools
"""

import argparse
import json
import time
import uuid

from harness import kafka_log, settings, stage0, turn
from harness.context import assemble_system_prompt
from harness.session import Session


def ask(questions: list[str]) -> None:
    session_id = f"rehearse-{uuid.uuid4().hex[:8]}"
    for number, question in enumerate(questions, start=1):
        print(f"\n> {question}")
        outcome = turn.handle(Session(session_id, lambda line: print(f"  {line}")), question, number)
        print(outcome.report())


def bakeoff(runs: int) -> None:
    passed, steps, seconds, tool_calls = 0, 0, 0.0, 0
    for run in range(1, runs + 1):
        session = Session(f"bakeoff-{uuid.uuid4().hex[:8]}", lambda _: None)
        started = time.monotonic()
        outcome = turn.handle(session, settings.TASK_PROMPT, 1)
        elapsed = time.monotonic() - started
        calls = sum(len(e["data"]["calls"]) for e in session.events() if e["type"] == "assistant/tool_call")
        verdict = outcome.verdict.passed if outcome.verdict else None
        passed += verdict is True
        steps, seconds, tool_calls = steps + session.step, seconds + elapsed, tool_calls + calls
        answer = " ".join(outcome.answer.split())[:90]
        print(f"run {run:>2}  {str(verdict):<5}  {session.step} steps  {calls} tools  {elapsed:5.1f}s  {answer}")
    print(
        f"\n{settings.MODEL}: {passed}/{runs} verified, {steps / runs:.1f} steps, "
        f"{tool_calls / runs:.1f} tool calls, {seconds / runs:.1f}s per run"
    )


def stage0_runs(runs: int) -> None:
    """Stage 0 N times in fresh sessions, whatever is in harness/src: which order_ids does the model invent?"""
    real = {row["value"].get("order_id") for row in kafka_log.read(settings.PAYMENTS_TOPIC)}
    invented, settings.STAGE0_JSON = [], True
    for run in range(1, runs + 1):
        session = Session(f"stage0-{uuid.uuid4().hex[:8]}", lambda _: None)
        session.turn = 1
        session.append("system/prompt", content=assemble_system_prompt())
        session.append("user/message", content=settings.TASK_PROMPT)
        answer = stage0.ask(session).answer
        try:
            order_id = json.loads(answer).get("order_id")
        except json.JSONDecodeError:
            order_id = None
        invented.append(order_id)
        print(f"run {run:>2}  {str(order_id)!r:<16}  {' '.join(answer.split())[:90]}")
    on_kafka = sum(order_id in real for order_id in invented)
    print(f"\n{settings.MODEL}: {len(set(invented))} different order_ids in {runs} runs, {on_kafka} real ones")


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("ask").add_argument("questions", nargs="+")
    bake = commands.add_parser("bakeoff")
    bake.add_argument("--runs", type=int, default=10)
    bake.add_argument("--model", default=settings.MODEL)
    commands.add_parser("stage0").add_argument("--runs", type=int, default=5)
    args = parser.parse_args()
    if args.command == "ask":
        ask(args.questions)
    elif args.command == "stage0":
        stage0_runs(args.runs)
    else:
        settings.MODEL = args.model
        bakeoff(args.runs)


if __name__ == "__main__":
    main()

"""Check the whole stack from inside the harness container: `make doctor`."""

import sys

import httpx

from harness import kafka_log, lenses, oauth, settings

OPENCODE_URL = "http://opencode:4096"


def kafka() -> str:
    kafka_log.wait_until_ready(timeout=10)
    return settings.KAFKA_BOOTSTRAP


def topics() -> str:
    payments = kafka_log.end_offset(settings.PAYMENTS_TOPIC)
    if payments != 5:
        raise RuntimeError(f"{settings.PAYMENTS_TOPIC} has {payments} records, expected 5. Run `make reset`")
    events = kafka_log.end_offset(settings.SESSION_TOPIC)
    return f"{settings.PAYMENTS_TOPIC} has 5 records, {settings.SESSION_TOPIC} has {events} events"


def login() -> str:
    return oauth.status()


def mcp() -> str:
    return f"{len(lenses.list_tools())} tools at {settings.LENSES_MCP_URL}"


def environment() -> str:
    environments = lenses.call("list_environments", {})
    match = next((e for e in environments if e.get("name") == settings.LENSES_ENVIRONMENT), None)
    if match is None:
        raise RuntimeError(f"no Lenses environment called {settings.LENSES_ENVIRONMENT!r} yet")
    if not match.get("status", {}).get("agent_connected"):
        raise RuntimeError("the Lenses Agent has not connected to HQ yet. Give it a minute")
    return f"{settings.LENSES_ENVIRONMENT} connected"


def ollama() -> str:
    tags = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=10).json()
    names = {m["name"] for m in tags.get("models", [])}
    if settings.MODEL not in names and f"{settings.MODEL}:latest" not in names:
        raise RuntimeError(f"{settings.MODEL} is missing at {settings.OLLAMA_URL}. Run `ollama pull {settings.MODEL}`")
    shown = httpx.post(f"{settings.OLLAMA_URL}/api/show", json={"model": settings.MODEL}, timeout=10).json()
    if "tools" not in shown.get("capabilities", []):
        raise RuntimeError(f"{settings.MODEL} does not support tool calling")
    return f"{settings.MODEL} at {settings.OLLAMA_URL}"


def harness() -> str:
    httpx.get("http://localhost:8080/v1/models", timeout=5).raise_for_status()
    return "http://localhost:8080/v1"


def opencode() -> str:
    status = httpx.get(OPENCODE_URL, timeout=5).status_code
    if status >= 500:
        raise RuntimeError(f"OpenCode answered {status}")
    return "http://localhost:4096"


CHECKS = [
    ("Kafka", kafka),
    ("Topics", topics),
    ("Lenses login", login),
    ("Lenses MCP", mcp),
    ("Lenses environment", environment),
    ("Ollama", ollama),
    ("Harness API", harness),
    ("OpenCode", opencode),
]


def main() -> int:
    failures = 0
    for name, check in CHECKS:
        try:
            print(f"✓ {name:<19} {check()}")
        except Exception as exc:
            failures += 1
            print(f"✗ {name:<19} {exc}")
    print("\nAll good. Open http://localhost:4096" if not failures else f"\n{failures} check(s) failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

from harness import settings
from harness.guardrails import check_caps, check_tool


def test_a_select_may_run():
    assert check_tool("execute_sql", {"sql": "SELECT * FROM payments LIMIT 20"}).allowed
    assert check_tool("execute_sql", {"sql": "  select * from payments;"}).allowed


def test_an_insert_is_blocked():
    decision = check_tool("execute_sql", {"sql": "INSERT INTO payments(_key, amount) VALUES ('ord_z9', 1)"})
    assert decision.blocked
    assert "SELECT" in decision.reason


def test_stacked_statements_are_blocked():
    assert check_tool("execute_sql", {"sql": "SELECT 1; DELETE FROM payments"}).blocked


def test_an_empty_query_is_blocked():
    assert check_tool("execute_sql", {"sql": ""}).blocked


def test_the_session_log_is_off_limits():
    assert check_tool("execute_sql", {"sql": f"SELECT * FROM `{settings.SESSION_TOPIC}`"}).blocked


def test_other_tools_pass_through():
    assert check_tool("list_topics", {"name_filter": ""}).allowed


def test_caps_end_the_turn():
    assert check_caps(0, 0).allowed
    assert check_caps(settings.MAX_STEPS, 0).blocked
    assert check_caps(0, settings.RUN_TOKEN_BUDGET).blocked

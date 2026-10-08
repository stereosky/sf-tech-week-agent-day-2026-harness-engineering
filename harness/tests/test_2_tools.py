from harness import lenses, tools


def test_the_menu_has_the_two_lenses_tools():
    assert {"list_topics", "execute_sql"} <= set(tools.registry().tools)


def test_the_menu_stays_small():
    assert len(tools.registry().tools) <= 4


def test_the_harness_hides_the_environment_argument():
    for schema in tools.registry().schemas():
        assert "environment" not in schema["function"]["parameters"].get("properties", {})


def test_every_tool_has_a_required_parameter():
    # Ollama drops tool calls that arrive with no arguments at all.
    for schema in tools.registry().schemas():
        assert schema["function"]["parameters"].get("required")


def test_mistakes_come_back_as_text_the_model_can_read():
    registry = tools.Registry([tools.READ_FILE])
    assert registry.run("drop_table", {}).startswith("error: there is no tool")
    assert registry.run("read_file", {}).startswith("error: read_file needs path")
    assert registry.run("read_file", {"path": "../../etc/passwd"}).startswith("error:")
    assert "list_topics" in registry.run("read_file", {"path": "AGENTS.md"})


def test_topics_are_shaped_for_a_small_model():
    topics = [
        {"topicName": "payments", "totalMessages": 5, "valueType": "JSON"},
        {"topicName": "agent.session", "totalMessages": 99, "valueType": "JSON"},
        {"topicName": "__consumer_offsets", "isControlTopic": True},
    ]
    shaped = lenses.shape_topics(topics, "")
    assert shaped == "payments  (5 messages, value format JSON)"
    assert "No topics match" in lenses.shape_topics(topics, "orders")


def test_an_empty_sql_result_says_why_it_might_be_empty():
    assert "invalid" in lenses.shape_rows([])
    assert lenses.shape_rows([{"key": "ord_a1", "value": {"amount": 1}}]) == 'key=ord_a1 value={"amount": 1}'

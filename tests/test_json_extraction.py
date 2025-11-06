from app.services.agent_graph import AgentGraph


def test_extract_from_json_embedded_prose():
    ag = AgentGraph()
    raw = (
        "Here you go:\n"
        "{"  # start JSON
        "\n  \"reasoning_steps\": [\"a\", \"b\", \"c\"],\n"
        "  \"outgoing_message\": \"Hello there\",\n"
        "  \"crm_stage\": \"Qualifying\",\n"
        "  \"next_action_suggested\": \"escalate_scheduling\"\n"
        "}"  # end JSON
        "\nThanks!"
    )
    msg, act = ag._extract_from_json(raw)
    assert msg == "Hello there"
    assert isinstance(act, dict)
    assert act.get("action") == "escalate_scheduling"


def test_extract_from_json_object_suggestion():
    ag = AgentGraph()
    raw = (
        "{\n"
        "  \"reasoning_steps\": [\"a\"],\n"
        "  \"outgoing_message\": \"Yo\",\n"
        "  \"crm_stage\": \"Working\",\n"
        "  \"next_action_suggested\": {\"action\": \"request_application\", \"reason\": \"ok\"}\n"
        "}"
    )
    msg, act = ag._extract_from_json(raw)
    assert msg == "Yo"
    assert act == {"action": "request_application"}





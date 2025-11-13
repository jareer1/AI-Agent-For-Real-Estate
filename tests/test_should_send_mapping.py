from app.services.actions import determine_should_send


def test_should_send_mappings():
    # No-send categories regardless of stage (except complaint special-case)
    assert determine_should_send("escalate_links", "working") is False
    assert determine_should_send("escalate_fees", "qualifying") is False
    assert determine_should_send("escalate_pricing", "working") is False

    # Complaint: send unless post-close states
    assert determine_should_send("escalate_complaint", "working") is True
    assert determine_should_send("escalate_complaint", "approved") is False
    assert determine_should_send("escalate_complaint", "closed") is False
    assert determine_should_send("escalate_complaint", "post-close nurture") is False

    # Send categories
    assert determine_should_send("escalate_more_options", "working") is True
    assert determine_should_send("escalate_scheduling", "touring") is True
    assert determine_should_send("escalate_approved", "approved") is True
    assert determine_should_send("escalate_followup", "working") is True
    assert determine_should_send("escalate_general", "qualifying") is True

    # Unknown action defaults to send
    assert determine_should_send("unknown_action", "working") is True








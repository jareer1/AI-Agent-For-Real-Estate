"""Test that the updated prompts include repetition prevention."""

import sys
sys.path.insert(0, 'app/services')

from prompts import get_system_prompt

def test_repetition_prevention():
    """Test that repetition prevention guidance is included."""
    prompt = get_system_prompt()

    print("Checking for repetition prevention guidance...")
    print(f"Prompt length: {len(prompt)}")

    # Check for repetition prevention
    checks = [
        "DON'T REPEAT THE SAME ESCALATION",
        "CHECK IF ACTIONS ARE ALREADY IN PROGRESS",
        "ADVANCE THE CONVERSATION",
        "ONE ESCALATION PER TOPIC",
        "ONCE TOUR SCHEDULING IS HANDLED",
        "REPEAT THE SAME ESCALATION",
        "KEEP PROMISING THE SAME ACTION"
    ]

    for check in checks:
        if check in prompt:
            print(f"✅ Found: {check}")
        else:
            print(f"❌ Missing: {check}")

    # Required checks - these will fail the test if not found
    required_checks = [
        "DON'T REPEAT THE SAME ESCALATION",
        "CHECK IF ACTIONS ARE ALREADY IN PROGRESS",
        "ADVANCE THE CONVERSATION",
        "ONE ESCALATION PER TOPIC"
    ]

    for check in required_checks:
        assert check in prompt, f"Required guidance missing: {check}"

    print("✅ Repetition prevention guidance correctly included")

def test_escalation_history_tracking():
    """Test that escalation history tracking is included."""
    prompt = get_system_prompt()

    # Check for escalation history tracking
    assert "Track Escalation History:" in prompt
    assert "Previous escalations" in prompt
    assert "what you've already escalated for" in prompt
    assert "When NOT to Escalate" in prompt
    print("✅ Escalation history tracking correctly included")

def test_tour_stage_guidance():
    """Test that touring stage has repetition prevention."""
    prompt = get_system_prompt()

    # Check touring stage guidance
    assert "ONCE TOUR SCHEDULING IS HANDLED, STOP REPEATING TOUR ESCALATIONS" in prompt
    assert "move conversation forward" in prompt
    print("✅ Touring stage repetition prevention correctly included")

if __name__ == "__main__":
    print("Testing repetition prevention updates...\n")

    try:
        test_repetition_prevention()
        test_escalation_history_tracking()
        test_tour_stage_guidance()

        print("\n" + "="*60)
        print("✅ ALL TESTS PASSED")
        print("="*60)
        print("\nRepetition prevention updates successful:")
        print("  - Chat history checking emphasized")
        print("  - Repetition prevention guidance added")
        print("  - Escalation history tracking included")
        print("  - Touring stage updated to advance conversation")

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

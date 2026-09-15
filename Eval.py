"""
eval.py — behavioral tests for the assistant, not just keyword matching.

The previous version only checked "does the reply text contain word X?" —
that can pass even if the model never called a tool and just guessed, or
fail on a perfectly good reply phrased differently. This version checks
what the model actually DID: which tools it called, with what arguments,
and whether the expected side effects (like a real booking row) exist in
the database — plus a light text check as one signal among several, not
the only one.

Uses assistant.process_message_with_trace(), which returns
(final_text, tool_calls) — tool_calls is a list of
{"name": ..., "input": ..., "result": ...} for every tool the model
actually invoked during the conversation.

Note: calls the real API for every test case — costs a few cents per
run, don't loop it constantly.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    python3 eval.py
"""

import uuid
from assistant import process_message_with_trace
import database


def new_phone_number():
    return f"+1eval{uuid.uuid4().hex[:8]}"


def called_tool(tool_calls, name):
    return [t for t in tool_calls if t["name"] == name]


def contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


# ---------- Individual check functions ----------
# Each returns (passed: bool, detail: str)

def check_rag_grounded(expected_keywords):
    """Confirms the model actually searched the knowledge base (not just
    guessed) AND that the reply reflects what was retrieved."""
    def check(final_text, tool_calls, phone_number):
        searches = called_tool(tool_calls, "search_knowledge_base")
        if not searches:
            return False, "search_knowledge_base was not called - answer may not be grounded in real data"
        if not contains_any(final_text, expected_keywords):
            return False, f"reply doesn't mention any of {expected_keywords}"
        return True, f"searched KB ({len(searches)}x) and reply matched expected content"
    return check


def check_no_hallucination(decline_keywords):
    """For questions the knowledge base has no answer to - the model
    should decline/redirect, not invent an answer."""
    def check(final_text, tool_calls, phone_number):
        if not contains_any(final_text, decline_keywords):
            return False, f"expected a decline/redirect phrase from {decline_keywords} - possible hallucination"
        return True, "model declined instead of inventing an answer"
    return check


def check_booking_end_to_end(final_text, tool_calls, phone_number):
    """The full chain: intent recognized -> tool called -> right args ->
    real DB row created -> correct customer -> confirmation in reply."""
    booking_calls = called_tool(tool_calls, "start_booking")
    if not booking_calls:
        return False, "start_booking was never called - booking intent not recognized"

    call = booking_calls[0]
    date = call["input"].get("preferred_date")
    time = call["input"].get("preferred_time")
    if not date or not time:
        return False, f"start_booking called with missing args: {call['input']}"

    db_bookings = database.get_bookings(phone_number)
    if not db_bookings:
        return False, "start_booking was called but no row exists in the bookings table"

    # row shape: (id, phone_number, preferred_date, preferred_time, status, created_at)
    matching = [b for b in db_bookings if b[1] == phone_number]
    if not matching:
        return False, "booking exists but isn't associated with the correct phone number"

    if not contains_any(final_text, ["book", "confirm", "saturday", "2pm", "scheduled", "set"]):
        return False, f"booking was created but reply doesn't confirm it: {final_text!r}"

    return True, f"booking created (date={date}, time={time}) and confirmed to customer"


# ---------- Test cases ----------

TEST_CASES = [
    {
        "name": "outdoor wedding question (RAG)",
        "message": "do you handle outdoor weddings?",
        "check": check_rag_grounded(["outdoor", "tent", "weather"]),
    },
    {
        "name": "cancellation policy question (RAG)",
        "message": "what's your cancellation policy?",
        "check": check_rag_grounded(["deposit", "refund", "cancel"]),
    },
    {
        "name": "pricing question (RAG)",
        "message": "how much for tables and chairs?",
        "check": check_rag_grounded(["500", "r500", "table", "chair"]),
    },
    {
        "name": "business hours question (RAG)",
        "message": "what are your business hours?",
        "check": check_rag_grounded(["monday", "saturday", "9am", "hours"]),
    },
    {
        "name": "wheelchair accessibility question (RAG)",
        "message": "can you set up for a wheelchair accessible event?",
        "check": check_rag_grounded(["wheelchair", "accessib", "yes"]),
    },
    {
        "name": "unknown info - should not hallucinate",
        "message": "do you rent helicopters for events?",
        "check": check_no_hallucination(["check", "don't", "not sure", "team", "no"]),
    },
    {
        "name": "booking intent - full chain",
        "message": "I'd like to book for next Saturday at 2pm",
        "check": check_booking_end_to_end,
    },
]


def run_eval():
    passed = 0
    failed = 0

    for case in TEST_CASES:
        phone_number = new_phone_number()
        try:
            final_text, tool_calls = process_message_with_trace(phone_number, case["message"])
            ok, detail = case["check"](final_text, tool_calls, phone_number)
        except Exception as e:
            print(f"ERROR   | {case['name']} | exception: {e}")
            failed += 1
            continue

        status = "PASS" if ok else "FAIL"
        passed += ok
        failed += not ok

        print(f"{status}   | {case['name']}")
        print(f"        message     : {case['message']}")
        print(f"        tools called: {[t['name'] for t in tool_calls] or 'none'}")
        print(f"        reply       : {final_text}")
        print(f"        detail      : {detail}")
        print()

    total = passed + failed
    print("-" * 50)
    print(f"Results: {passed}/{total} passed")


if __name__ == "__main__":
    run_eval()

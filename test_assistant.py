"""
test_assistant.py — pytest version of the eval suite. Same behavioral
checks as eval.py (real tool calls + database state, not keyword
matching), rewritten as a proper pytest suite with fixtures.

Run with:
    export ANTHROPIC_API_KEY="sk-ant-..."
    pytest test_assistant.py -v

Note: every test calls the real Claude API - costs a small amount of
tokens per run. Not meant for CI on every commit; run it before merging
prompt/tool changes.
"""

import uuid
import pytest

from assistant import process_message_with_trace
import database


# ---------- Fixtures ----------

@pytest.fixture
def phone_number():
    """A fresh, unique phone number per test so conversations and
    bookings never bleed between test cases."""
    return f"+1eval{uuid.uuid4().hex[:8]}"


@pytest.fixture(autouse=True)
def ensure_db():
    """Make sure the database schema exists before any test runs."""
    database.init_db()


# ---------- Helpers ----------

def called_tool(tool_calls, name):
    return [t for t in tool_calls if t["name"] == name]


def contains_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(k.lower() in lower for k in keywords)


# ---------- RAG grounding tests ----------
# Parametrized: each tuple is (test id, message, expected keywords).
# All share the same assertion logic - did it search, did the reply match.

RAG_CASES = [
    ("outdoor_wedding", "do you handle outdoor weddings?", ["outdoor", "tent", "weather"]),
    ("cancellation_policy", "what's your cancellation policy?", ["deposit", "refund", "cancel"]),
    ("pricing", "how much for tables and chairs?", ["500", "r500", "table", "chair"]),
    ("business_hours", "what are your business hours?", ["monday", "saturday", "9am", "hours"]),
    ("wheelchair_access", "can you set up for a wheelchair accessible event?", ["wheelchair", "accessib", "yes"]),
]


@pytest.mark.parametrize("message,expected_keywords", [(m, k) for _, m, k in RAG_CASES],
                          ids=[name for name, _, _ in RAG_CASES])
def test_rag_answers_are_grounded(phone_number, message, expected_keywords):
    """The model should search the knowledge base before answering
    business questions, and the reply should reflect what it found."""
    final_text, tool_calls = process_message_with_trace(phone_number, message)

    searches = called_tool(tool_calls, "search_knowledge_base")
    assert searches, "search_knowledge_base was not called - answer may not be grounded in real data"

    assert contains_any(final_text, expected_keywords), (
        f"reply doesn't mention any of {expected_keywords}. Got: {final_text!r}"
    )


def test_model_does_not_hallucinate_unknown_info(phone_number):
    """For something the knowledge base has no answer to, the model
    should decline or redirect rather than inventing details."""
    final_text, tool_calls = process_message_with_trace(
        phone_number, "do you rent helicopters for events?"
    )

    decline_keywords = ["check", "don't", "not sure", "team", "no"]
    assert contains_any(final_text, decline_keywords), (
        f"expected a decline/redirect phrase, possible hallucination. Got: {final_text!r}"
    )


# ---------- Booking: the full end-to-end chain ----------

def test_booking_full_chain(phone_number):
    """Checks every link in the chain, not just the reply text:
    intent recognized -> tool called -> valid args -> real DB row ->
    correct customer -> confirmed in the reply."""
    message = "I'd like to book for next Saturday at 2pm"
    final_text, tool_calls = process_message_with_trace(phone_number, message)

    booking_calls = called_tool(tool_calls, "start_booking")
    assert booking_calls, "start_booking was never called - booking intent not recognized"

    call = booking_calls[0]
    date = call["input"].get("preferred_date")
    time = call["input"].get("preferred_time")
    assert date and time, f"start_booking called with missing args: {call['input']}"

    db_bookings = database.get_bookings(phone_number)
    assert db_bookings, "start_booking was called but no row exists in the bookings table"

    # row shape: (id, phone_number, preferred_date, preferred_time, status, created_at)
    matching = [b for b in db_bookings if b[1] == phone_number]
    assert matching, "booking exists but isn't associated with the correct phone number"

    assert contains_any(final_text, ["book", "confirm", "saturday", "2pm", "scheduled", "set"]), (
        f"booking was created but reply doesn't confirm it: {final_text!r}"
    )


# ---------- Structured output classification ----------

def test_interaction_gets_classified(phone_number):
    """After a message, an interaction_logs row should exist with a
    real classification - proves the structured-output tool call ran."""
    process_message_with_trace(phone_number, "this is taking too long, I need an answer now")

    logs = database.get_interaction_logs(phone_number)
    assert logs, "no interaction_logs row was created - classify_interaction may have failed silently"

    # row shape: (id, phone_number, category, sentiment, urgency, created_at)
    latest = logs[-1]
    assert latest[2] and latest[3] and latest[4], f"classification fields incomplete: {latest}"

"""
assistant.py — Claude-powered brain, now with per-customer memory and
real booking persistence.

Changes from the previous version:
- process_message() now takes phone_number, so each customer gets their
  own conversation context instead of one shared global history.
- start_booking() actually writes to the bookings table via database.py,
  instead of just returning a fake confirmation.
"""

import json
from anthropic import Anthropic
import database

MODEL = "claude-sonnet-4-6"
client = Anthropic()  # reads ANTHROPIC_API_KEY from environment

SYSTEM_PROMPT = """You are the WhatsApp Business Assistant for a small business.
Greet customers warmly, answer questions about pricing and hours using the
tools provided (never guess), and help them book by collecting a preferred
date and time, then confirming with the start_booking tool. Keep replies
short and friendly, like a real WhatsApp message - one or two sentences,
no markdown formatting."""


def _make_tool_functions(phone_number: str):
    """Tool implementations, bound to the current customer's phone number
    so bookings get attributed correctly."""

    def get_price_info():
        # TODO: replace with real pricing data / DB lookup
        return {"starting_price": "R500", "note": "Price depends on the service requested."}

    def get_business_hours():
        return {"hours": "Monday to Saturday, 9am - 5pm"}

    def start_booking(preferred_date: str, preferred_time: str):
        booking_id = database.create_booking(phone_number, preferred_date, preferred_time)
        return {
            "booking_id": booking_id,
            "status": "pending",
            "preferred_date": preferred_date,
            "preferred_time": preferred_time,
        }

    return {
        "get_price_info": get_price_info,
        "get_business_hours": get_business_hours,
        "start_booking": start_booking,
    }


TOOLS = [
    {
        "name": "get_price_info",
        "description": "Get the business's starting price and pricing note.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_business_hours",
        "description": "Get the business's operating hours.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "start_booking",
        "description": "Create a booking once the customer has given both a preferred date and time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "preferred_date": {"type": "string"},
                "preferred_time": {"type": "string"},
            },
            "required": ["preferred_date", "preferred_time"],
        },
    },
]


def _build_history(phone_number: str):
    rows = database.get_recent_messages(phone_number, limit=10)
    history = []
    for row in rows:
        # row shape: (id, phone_number, user_message, bot_response, created_at)
        _, _, user_msg, bot_msg, _ = row
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_msg})
    return history


def process_message(phone_number: str, message: str) -> str:
    tool_functions = _make_tool_functions(phone_number)
    history = _build_history(phone_number)
    history.append({"role": "user", "content": message})

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=history,
        )

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            return "".join(
                block.text for block in response.content if block.type == "text"
            )

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = tool_functions[block.name]
                result = fn(**block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

        history.append({"role": "user", "content": tool_results})

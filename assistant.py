"""
assistant.py — now reads the customer's profile automatically at the
start of every conversation (like a mounted memory store) and can update
it via the update_customer_profile tool when it learns something durable.
"""

import json
from anthropic import Anthropic
import database

MODEL = "claude-sonnet-4-6"
client = Anthropic()  # reads ANTHROPIC_API_KEY from environment

BASE_SYSTEM_PROMPT = """You are the WhatsApp Business Assistant for a small business.
Greet customers warmly, answer questions about pricing and hours using the
tools provided (never guess), and help them book by collecting a preferred
date and time, then confirming with the start_booking tool. Keep replies
short and friendly, like a real WhatsApp message - one or two sentences,
no markdown formatting.

You have access to this customer's saved profile below. Use it naturally
(e.g. "welcome back!" or referencing a known preference) - don't recite it
back like a report. When the customer shares something worth remembering
for next time - a preference, an event type they usually book, a note like
"always needs wheelchair access" - save it with update_customer_profile.
Only save durable facts, not one-off chat details."""


def _make_tool_functions(phone_number: str):
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

    def update_customer_profile(key: str, value: str):
        profile = database.update_customer_profile(phone_number, key, value)
        return {"saved": True, "profile": profile}

    return {
        "get_price_info": get_price_info,
        "get_business_hours": get_business_hours,
        "start_booking": start_booking,
        "update_customer_profile": update_customer_profile,
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
    {
        "name": "update_customer_profile",
        "description": (
            "Save a durable fact about this customer for future conversations "
            "(e.g. preferred event type, accessibility needs, recurring preferences). "
            "Do not use this for one-off details that only matter in this chat."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Short label, e.g. 'preferred_event_type'"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
]


def _build_history(phone_number: str):
    rows = database.get_recent_messages(phone_number, limit=10)
    history = []
    for row in rows:
        _, _, user_msg, bot_msg, _ = row
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_msg})
    return history


def _build_system_prompt(phone_number: str) -> str:
    profile = database.get_customer_profile(phone_number)
    if profile:
        profile_text = json.dumps(profile, indent=2)
    else:
        profile_text = "(no profile yet - this is a new or unknown customer)"
    return f"{BASE_SYSTEM_PROMPT}\n\nCustomer profile:\n{profile_text}"


def process_message(phone_number: str, message: str) -> str:
    tool_functions = _make_tool_functions(phone_number)
    system_prompt = _build_system_prompt(phone_number)
    history = _build_history(phone_number)
    history.append({"role": "user", "content": message})

    while True:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=system_prompt,
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


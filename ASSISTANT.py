"""
assistant.py — now answers pricing/hours/policy/FAQ questions via RAG
(rag.py) instead of hardcoded stubs. Claude searches the knowledge base
and answers from the retrieved text, rather than guessing.

Keeps the customer memory (customer_profiles) and booking tools from the
previous upgrade.
"""

import json
from anthropic import Anthropic
import database
from rag import search_knowledge_base

MODEL = "claude-sonnet-4-6"
client = Anthropic()  # reads ANTHROPIC_API_KEY from environment

BASE_SYSTEM_PROMPT = """You are the WhatsApp Business Assistant for a small
event rental business. Greet customers warmly and keep replies short and
friendly, like a real WhatsApp message - one or two sentences, no markdown
formatting.

For ANY question about services, pricing, hours, policies, or FAQs, use the
search_knowledge_base tool first and answer only from what it returns.
Never guess or make up details. If the knowledge base doesn't have the
answer, say you'll check with the team rather than inventing one.

Help customers book by collecting a preferred date and time, then
confirming with the start_booking tool.

You have access to this customer's saved profile below. Use it naturally
- don't recite it back like a report. When the customer shares something
worth remembering for next time (a preference, event type, accessibility
need), save it with update_customer_profile. Only save durable facts."""


def _make_tool_functions(phone_number: str):
    def search_knowledge_base_tool(query: str):
        results = search_knowledge_base(query, top_k=3)
        if not results:
            return {"results": [], "note": "No matching information found in the knowledge base."}
        return {"results": results}

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
        "search_knowledge_base": search_knowledge_base_tool,
        "start_booking": start_booking,
        "update_customer_profile": update_customer_profile,
    }


TOOLS = [
    {
        "name": "search_knowledge_base",
        "description": (
            "Search the business's knowledge base (services, pricing, hours, "
            "policies, FAQs) for information relevant to the customer's question. "
            "Always use this before answering questions about the business - "
            "never rely on memory or guesswork for these details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The customer's question or topic, in plain language"}
            },
            "required": ["query"],
        },
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
    profile_text = json.dumps(profile, indent=2) if profile else "(no profile yet - new or unknown customer)"
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

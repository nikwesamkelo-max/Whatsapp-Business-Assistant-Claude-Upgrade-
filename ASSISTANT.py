"""
assistant.py — adds three course upgrades on top of the RAG version:

1. Prompt caching: the static system prompt + tool definitions are marked
   with cache_control, so repeat requests are cheaper and faster. Only the
   per-customer profile (which changes) stays outside the cached block.

2. Structured outputs: after replying, a second forced-tool-call classifies
   the interaction (category/sentiment/urgency) into interaction_logs -
   real analytics data, not free text you'd have to parse by hand.

3. Streaming: process_message_stream() yields the reply token-by-token
   using client.messages.stream(), for a more realistic chat feel.

No new dependencies - same anthropic SDK you already have.
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

Use the customer's saved profile naturally - don't recite it back like a
report. When the customer shares something worth remembering for next time
(a preference, event type, accessibility need), save it with
update_customer_profile. Only save durable facts.

If a customer sends a photo (e.g. of their venue), look at it and give
practical advice - what setup would suit the space, whether it looks
suitable for a tent, seating capacity it could hold, etc. Combine what
you see with the knowledge base rather than guessing at business details."""


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


# ---------- Tools (cache_control on the LAST one caches this entire block) ----------

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
        "cache_control": {"type": "ephemeral"},  # caches this + everything above it
    },
]


# ---------- Structured output tool (forced call, used for classification only) ----------

CLASSIFY_TOOL = [
    {
        "name": "classify_interaction",
        "description": "Classify this customer interaction for analytics purposes.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["pricing_inquiry", "booking", "policy_question", "complaint", "general", "faq"],
                },
                "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
                "urgency": {"type": "string", "enum": ["low", "medium", "high"]},
            },
            "required": ["category", "sentiment", "urgency"],
        },
    }
]


def _classify_interaction(phone_number: str, user_message: str, bot_response: str):
    """A second, separate API call that forces a structured classification
    via tool_choice. Kept independent from the main conversation so a
    classification hiccup never breaks the customer-facing reply."""
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=200,
            tools=CLASSIFY_TOOL,
            tool_choice={"type": "tool", "name": "classify_interaction"},
            messages=[{
                "role": "user",
                "content": f"Customer said: {user_message!r}\nAssistant replied: {bot_response!r}",
            }],
        )
        for block in response.content:
            if block.type == "tool_use":
                data = block.input
                database.log_interaction(
                    phone_number, data["category"], data["sentiment"], data["urgency"]
                )
    except Exception as e:
        # Analytics should never take down the main assistant.
        print(f"[classify_interaction] skipped due to error: {e}")


# ---------- Shared helpers ----------

def _build_history(phone_number: str):
    rows = database.get_recent_messages(phone_number, limit=10)
    history = []
    for row in rows:
        _, _, user_msg, bot_msg, _ = row
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": bot_msg})
    return history


def _build_system_prompt(phone_number: str):
    """Returns system as a list of blocks: the static instructions are
    cached (cache_control), the per-customer profile is appended fresh
    each time since it changes."""
    profile = database.get_customer_profile(phone_number)
    profile_text = json.dumps(profile, indent=2) if profile else "(no profile yet - new or unknown customer)"

    return [
        {
            "type": "text",
            "text": BASE_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": f"Customer profile:\n{profile_text}",
        },
    ]


# ---------- Non-streaming (unchanged behavior, now with caching + logging) ----------

def _run_conversation(phone_number: str, message: str, image_base64: str = None, image_media_type: str = None):
    """Core loop, shared by process_message() and process_message_with_trace().
    Returns (final_text, tool_calls) where tool_calls is a list of
    {"name": ..., "input": ..., "result": ...} for every tool Claude
    actually called - this is what makes real eval assertions possible,
    instead of guessing from the reply text alone.

    If image_base64 is given, the message is sent as a multimodal turn
    (image + text) - e.g. a customer sending a venue photo. No extra
    dependencies needed; Claude does the actual image reasoning, we just
    pass the bytes along."""
    tool_functions = _make_tool_functions(phone_number)
    system_prompt = _build_system_prompt(phone_number)
    history = _build_history(phone_number)

    if image_base64:
        user_content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type or "image/jpeg",
                    "data": image_base64,
                },
            },
            {"type": "text", "text": message},
        ]
        logged_message = f"[image attached] {message}"
    else:
        user_content = message
        logged_message = message

    history.append({"role": "user", "content": user_content})

    tool_calls = []

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
            final_text = "".join(
                block.text for block in response.content if block.type == "text"
            )
            database.save_message(phone_number, logged_message, final_text)
            _classify_interaction(phone_number, logged_message, final_text)
            return final_text, tool_calls

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = tool_functions[block.name]
                result = fn(**block.input)
                tool_calls.append({"name": block.name, "input": block.input, "result": result})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )

        history.append({"role": "user", "content": tool_results})


def process_message(phone_number: str, message: str, image_base64: str = None, image_media_type: str = None) -> str:
    """Public entry point used by the API - same signature as before, plus
    optional image_base64/image_media_type for multimodal messages."""
    final_text, _ = _run_conversation(phone_number, message, image_base64, image_media_type)
    return final_text


def process_message_with_trace(phone_number: str, message: str):
    """Like process_message, but also returns which tools were called and
    with what arguments. Use this in eval.py - never rely on parsing the
    reply text to infer what the model *did*."""
    return _run_conversation(phone_number, message)


# ---------- Streaming variant ----------

def process_message_stream(phone_number: str, message: str):
    """Generator that yields text chunks as they arrive. Tool calls happen
    silently between chunks (nothing is yielded while a tool runs); only
    the model's actual text output streams to the caller."""
    tool_functions = _make_tool_functions(phone_number)
    system_prompt = _build_system_prompt(phone_number)
    history = _build_history(phone_number)
    history.append({"role": "user", "content": message})

    while True:
        collected_text = []
        with client.messages.stream(
            model=MODEL,
            max_tokens=512,
            system=system_prompt,
            tools=TOOLS,
            messages=history,
        ) as stream:
            for chunk in stream.text_stream:
                collected_text.append(chunk)
                yield chunk
            response = stream.get_final_message()

        history.append({"role": "assistant", "content": response.content})

        if response.stop_reason != "tool_use":
            final_text = "".join(collected_text)
            database.save_message(phone_number, message, final_text)
            _classify_interaction(phone_number, message, final_text)
            return

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

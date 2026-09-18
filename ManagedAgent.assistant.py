"""
managed_assistant.py — runs conversations through Claude Managed Agents
instead of the manual tool-use loop in assistant.py.

This is additive, not a replacement: assistant.py and the /message
endpoint keep working exactly as before. This module powers a separate
/message/managed endpoint so you can compare both approaches side by
side before fully migrating.

Requires setup_managed_agent.py to have been run once, with
MANAGED_AGENT_ID and MANAGED_ENVIRONMENT_ID set as environment variables.

Beta caveat: Managed Agents is a beta feature (managed-agents-2026-04-01).
Event field names below (event.type, event.content, event.name,
event.input, event.id) follow the current public docs, but beta APIs can
shift - if something breaks, check
https://platform.claude.com/docs/en/managed-agents/overview first.

Key difference from assistant.py's approach: session state (conversation
history) is stored server-side by Anthropic, keyed by session_id - we
only need to remember WHICH session belongs to which customer (see
database.get_agent_session / save_agent_session), not replay their
message history ourselves on every turn.
"""

import os
import json
from anthropic import Anthropic

import database
from assistant import _make_tool_functions  # reuse the same tool implementations

client = Anthropic()

AGENT_ID = os.environ.get("MANAGED_AGENT_ID")
ENVIRONMENT_ID = os.environ.get("MANAGED_ENVIRONMENT_ID")


def _get_or_create_session(phone_number: str) -> str:
    session_id = database.get_agent_session(phone_number)
    if session_id:
        return session_id

    if not AGENT_ID or not ENVIRONMENT_ID:
        raise RuntimeError(
            "MANAGED_AGENT_ID / MANAGED_ENVIRONMENT_ID not set. "
            "Run setup_managed_agent.py once and export the printed values."
        )

    session = client.beta.sessions.create(
        agent=AGENT_ID,
        environment_id=ENVIRONMENT_ID,
        title=f"WhatsApp - {phone_number}",
    )
    database.save_agent_session(phone_number, session.id)
    return session.id


def process_message_managed(phone_number: str, message: str) -> str:
    """Sends a message through the customer's persistent Managed Agents
    session (creating one on first contact) and returns the reply.
    Custom tool calls are executed locally, same as assistant.py."""
    session_id = _get_or_create_session(phone_number)
    tool_functions = _make_tool_functions(phone_number)

    final_text_parts = []

    with client.beta.sessions.events.stream(session_id) as stream:
        client.beta.sessions.events.send(
            session_id,
            events=[{
                "type": "user.message",
                "content": [{"type": "text", "text": message}],
            }],
        )

        for event in stream:
            if event.type == "agent.message":
                for block in event.content:
                    if block.type == "text":
                        final_text_parts.append(block.text)

            elif event.type == "agent.custom_tool_use":
                fn = tool_functions.get(event.name)
                if fn is None:
                    result = {"error": f"no local implementation for tool '{event.name}'"}
                else:
                    result = fn(**event.input)

                client.beta.sessions.events.send(
                    session_id,
                    events=[{
                        "type": "user.custom_tool_result",
                        "tool_use_id": event.id,
                        "content": json.dumps(result),
                    }],
                )

            elif event.type == "session.status_idle":
                break

    final_text = "".join(final_text_parts)
    database.save_message(phone_number, message, final_text)
    return final_text

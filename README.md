# WhatsApp Business Assistant — Claude API

A backend WhatsApp assistant for a small event rental business. Built
progressively while working through Anthropic's Claude Platform courses -
tool use, RAG, persistent memory, prompt caching, structured outputs,
evals, streaming, multimodal, and Managed Agents.

## File structure

```
whatsapp-course-upgrades/
├── main.py                    FastAPI app - all endpoints
├── assistant.py                 Claude "brain" - tools, caching, streaming, multimodal
├── managed_assistant.py           Alternate brain - runs on Claude Managed Agents
├── setup_managed_agent.py           One-time script: creates the managed agent
├── database.py                        SQLite layer - messages, bookings, profiles, logs, sessions
├── rag.py                               Retrieval engine (pure-Python TF-IDF, no ML deps)
├── eval.py                                Standalone behavioral regression script
├── test_assistant.py                        Same tests, as a pytest suite with fixtures
├── requirements.txt                           fastapi, uvicorn, anthropic, python-multipart, pytest
├── .gitignore                                   ignores whatsapp.db, .env, __pycache__
└── knowledge/
    ├── services.txt                              business services + pricing
    ├── hours_and_policies.txt                      hours, deposits, cancellation, delivery
    └── faq.txt                                       common customer questions
```

Nothing here needs compiling - everything installs with plain `pip
install`, built and tested on a phone (Termux).

## What it does

- Answers pricing/hours/policy/FAQ questions, grounded in real documents
  via RAG - never guesses
- Creates bookings, tied to the customer's phone number
- Remembers customer preferences across separate conversations
- Classifies every interaction (category/sentiment/urgency) for analytics
- Accepts a photo (e.g. a venue) and reasons about it alongside text
- Can run through either a hand-built tool-use loop, or Claude Managed
  Agents - same tools, two different execution models, for comparison

## Upgrades, in the order they were built

1. **Tool use** — Claude calls real functions instead of keyword matching
2. **RAG** — answers grounded in `knowledge/*.txt` via hand-built TF-IDF
3. **Persistent memory** — `customer_profiles` table + `update_customer_profile` tool
4. **Prompt caching** — static system prompt + tools cached via `cache_control`
5. **Structured outputs** — forced `classify_interaction` tool call, logged per message
6. **Eval pipeline** — checks real tool calls and DB state, not keyword matching
7. **Streaming** — token-by-token replies via `client.messages.stream()`
8. **Multimodal** — `POST /message/image` lets a customer send a photo
9. **Managed Agents** — `managed_assistant.py` runs the same tools through
   Claude's managed session infrastructure instead of a manual loop

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
rm -f whatsapp.db   # schema grew again - new agent_sessions table
uvicorn main:app --reload
```

## Testing each piece

```bash
# Basic message
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=do%20you%20handle%20outdoor%20weddings"

# Streaming
curl --no-buffer "http://127.0.0.1:8000/message/stream?phone_number=+15551111111&text=tell%20me%20about%20your%20tents"

# Multimodal - send a photo (form upload)
curl -X POST "http://127.0.0.1:8000/message/image" \
  -F "phone_number=+15551111111" \
  -F "text=would this space work for a wedding?" \
  -F "image=@/path/to/venue.jpg"

# Structured output analytics
curl "http://127.0.0.1:8000/analytics"

# Customer profile / bookings
curl "http://127.0.0.1:8000/profile?phone_number=+15551111111"
curl "http://127.0.0.1:8000/bookings"

# Full behavioral eval suite (real API calls, costs a few cents)
python3 eval.py
# or the pytest version:
pytest test_assistant.py -v
```

## Using Managed Agents (beta, separate setup)

Managed Agents is a beta feature and may not be enabled on every account.
Run the one-time setup first:

```bash
python3 setup_managed_agent.py
# copy the two printed exports into your shell:
export MANAGED_AGENT_ID="agent_..."
export MANAGED_ENVIRONMENT_ID="env_..."
```

Then test the managed path alongside the regular one:

```bash
curl "http://127.0.0.1:8000/message/managed?phone_number=+15551111111&text=hi"
```

The `/message` endpoint (assistant.py) and `/message/managed` endpoint
(managed_assistant.py) use the *same* tool implementations, so you can
compare the two execution models directly. Session state for the managed
path lives server-side with Anthropic; we only track which session_id
belongs to which customer, in the new `agent_sessions` table.

Note: beta APIs can change field names/shapes between releases - if
`managed_assistant.py` errors on an event field, check
https://platform.claude.com/docs/en/managed-agents/overview for the
current schema before assuming the code is wrong.

## Good next exercises
- Batch/async the classify_interaction call so it doesn't add latency
- Build a small dashboard from interaction_logs (counts by category)
- Fully migrate off the manual loop once Managed Agents is validated
- Give the Managed Agents version a memory store (agent-memory-2026-07-22)
  for durable customer knowledge, instead of the custom SQLite profile table

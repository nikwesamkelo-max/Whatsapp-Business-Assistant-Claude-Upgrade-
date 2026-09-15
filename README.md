# WhatsApp Business Assistant — Claude API (Upgrades)

A backend WhatsApp assistant for a small event rental business. Built
progressively while working through Anthropic's Claude Platform courses -
tool use, RAG, persistent memory, prompt caching, structured outputs,
evals, and streaming.

## File structure

```
whatsapp-course-upgrades/
├── main.py               FastAPI app - all endpoints
├── assistant.py           Claude "brain" - tool use, caching, streaming
├── database.py             SQLite layer - messages, bookings, profiles, logs
├── rag.py                   Retrieval engine (pure-Python TF-IDF, no ML deps)
├── eval.py                   Behavioral regression tests
├── requirements.txt            fastapi, uvicorn, anthropic
├── .gitignore                    ignores whatsapp.db, .env, __pycache__
└── knowledge/
    ├── services.txt          business services + pricing
    ├── hours_and_policies.txt  hours, deposits, cancellation, delivery
    └── faq.txt                 common customer questions
```

Nothing here needs compiling - everything installs cleanly with plain
`pip install`, built and tested on a phone (Termux).

## What it does

Customers message the assistant (simulated via query params for now,
swap in a real WhatsApp webhook later) and it can:
- Answer pricing/hours/policy/FAQ questions, grounded in real documents
  via RAG - never guesses
- Create bookings, tied to the customer's phone number
- Remember customer preferences across separate conversations
- Classify every interaction (category/sentiment/urgency) for analytics

## Architecture

```
Customer message
      |
   FastAPI            <- main.py
      |
Claude assistant       <- assistant.py (tool-use loop)
      |
  -----------------------------
  |            |               |
Knowledge    Bookings      Customer
base (RAG)   (SQLite)      memory (SQLite)
  -----------------------------
      |
  Reply sent back
```

## Upgrades, in the order they were built

1. **Tool use** — Claude calls real functions (search, book, remember)
   instead of if/elif keyword matching.
2. **RAG** — pricing/hours/policy answers come from `knowledge/*.txt` via
   a hand-built TF-IDF + cosine similarity search (`rag.py`) - no vector
   DB, no embeddings API, nothing that needs compiling on a phone.
3. **Persistent memory** — `customer_profiles` table + an
   `update_customer_profile` tool, so returning customers get continuity.
4. **Prompt caching** — the static system prompt and tool definitions
   carry `cache_control`, so repeat requests reuse the cached prefix
   instead of reprocessing it every time.
5. **Structured outputs** — a second, forced tool call
   (`classify_interaction`) logs category/sentiment/urgency per message
   into `interaction_logs`, decoupled so it never breaks a customer reply.
6. **Eval pipeline** — `eval.py` checks real behavior, not keyword
   matching: did the model call the right tool, with the right arguments,
   and did the expected database row actually get created? See the
   booking test for the clearest example of this.
7. **Streaming** — `process_message_stream()` + `GET /message/stream`
   yields the reply token-by-token.

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
rm -f whatsapp.db   # fresh schema on first run
uvicorn main:app --reload
```

## Testing each piece

```bash
# Basic message
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=do%20you%20handle%20outdoor%20weddings"

# Streaming
curl --no-buffer "http://127.0.0.1:8000/message/stream?phone_number=+15551111111&text=tell%20me%20about%20your%20tents"

# Structured output analytics
curl "http://127.0.0.1:8000/analytics"

# Customer profile
curl "http://127.0.0.1:8000/profile?phone_number=+15551111111"

# Bookings
curl "http://127.0.0.1:8000/bookings"

# Full behavioral eval suite (uses real API - costs a few cents)
python3 eval.py
```

## Good next exercises
- Batch/async the classify_interaction call so it doesn't add latency
- Extend eval.py into a proper pytest suite with fixtures
- Build a small dashboard from interaction_logs (counts by category)
- Try multimodal: let a customer send a venue photo, still no heavy deps
- Migrate to Claude Platform Managed Agents for production-grade,
  resumable sessions (the natural next chapter)

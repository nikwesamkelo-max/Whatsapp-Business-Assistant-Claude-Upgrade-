# WhatsApp Business Assistant — Claude Upgrade (Phone Tracking + Real Bookings)

Full upgrade of your repo: replaces the rule-based brain with Claude,
tracks each customer's conversation separately by phone number, and makes
bookings real (persisted to SQLite) instead of simulated.

## What changed, file by file

**`database.py`**
- `messages` table now has a `phone_number` column + `created_at` timestamp
- New `bookings` table (id, phone_number, preferred_date, preferred_time, status, created_at)
- `get_all_messages(phone_number=None)` — filter by customer, or omit for everything
- New `get_recent_messages(phone_number, limit)` — powers Claude's memory
- New `create_booking()` / `get_bookings()`

**`assistant.py`**
- `process_message(phone_number, message)` — now takes phone_number (signature change from before)
- Pulls only *that customer's* history from SQLite, so conversations don't bleed into each other
- `start_booking` tool now actually calls `database.create_booking()` and returns a real booking id

**`main.py`**
- `/message` now requires `phone_number` and `text` query params
- `/history` accepts an optional `phone_number` filter
- New `/bookings` endpoint, same optional filter

## Setup

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload
```

## Test it — simulate two different customers

```bash
# Customer A
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=hi"
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=how%20much%20do%20you%20charge"

# Customer B — separate conversation, won't see Customer A's history
curl "http://127.0.0.1:8000/message?phone_number=+15552222222&text=what%20are%20your%20hours"

# Book an appointment
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=id%20like%20to%20book%20for%20next%20Friday%20at%203pm"

# Check results
curl "http://127.0.0.1:8000/history?phone_number=+15551111111"
curl "http://127.0.0.1:8000/bookings"
```

## Good next exercises
- Add a `status` update tool so staff (or Claude) can mark bookings
  "confirmed" / "cancelled"
- Add real pricing data behind `get_price_info` (a `services` table)
- Add prompt caching for `SYSTEM_PROMPT` once it grows
- Add basic input validation on `phone_number` format
- Add a `/bookings/{id}` endpoint to fetch or update a single booking
- Swap `curl` testing for a simple `pytest` suite calling the endpoints

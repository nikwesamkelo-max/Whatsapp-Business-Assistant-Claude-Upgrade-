
# WhatsApp Business Assistant — Customer Memory Upgrade

Adds a `customer_profiles` table and two new tools so Claude remembers
durable facts about each customer *across separate conversations*, not
just within one chat.

## How it relates to what you just read about Managed Agents

Claude Platform's real "memory stores" work similarly in spirit — Claude
reads a mounted file automatically at session start and writes to it when
it learns something worth keeping. Here, we're doing the same idea with
plain tool use on the standard Messages API:

| Managed Agents memory store | This version |
|---|---|
| Mounted as files under `/mnt/memory/` | A `customer_profiles` row in SQLite |
| Agent reads/writes with file tools automatically | Claude calls `update_customer_profile` explicitly |
| Injected into context via the sandbox mount | Injected into the system prompt each request |

When you get to the Managed Agents chapter, this is the concept you'll
already understand — just with a different mechanism.

## What changed

**`database.py`** — new `customer_profiles` table (`phone_number`,
`profile_json`, `updated_at`) with `get_customer_profile()` and
`update_customer_profile(phone_number, key, value)`.

**`assistant.py`**
- New `update_customer_profile` tool — Claude calls this when it learns
  something durable (preferred event type, accessibility needs, etc.)
- `_build_system_prompt()` now injects the customer's existing profile
  into the system prompt on every request, so Claude "remembers" them
  from the first message of a new conversation
- System prompt tells Claude to use the profile naturally, not recite it

**`main.py`** — new `GET /profile?phone_number=...` to inspect a
customer's saved profile directly.

## Test it — simulate a returning customer

```bash
# First conversation: customer mentions they always book weddings
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=hi%2C%20I%20run%20wedding%20events%20and%20always%20need%20round%20tables"

# Check what got saved
curl "http://127.0.0.1:8000/profile?phone_number=+15551111111"

# New "session" - same customer, fresh conversation - notice it remembers
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=hi%20again%2C%20need%20a%20quote"
```

## Good next exercises
- Add a `DELETE /profile` endpoint for GDPR-style "forget me" requests
- Cap how much profile data gets injected into the prompt (summarize if
  it grows large) — this is basically what Claude Platform's context
  editing/compaction does automatically for Managed Agents
- Add a `last_contacted` field and a tool to list customers who haven't
  messaged in 30+ days, for follow-up campaigns

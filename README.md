# WhatsApp Business Assistant — RAG Upgrade

Replaces the hardcoded `get_price_info`/`get_business_hours` stubs with
real retrieval-augmented generation over a text knowledge base.

## Why pure-Python TF-IDF instead of a vector library

Given you're on Termux, I deliberately avoided numpy/scikit-learn/
sentence-transformers — those often fail to build on mobile ARM without
precompiled wheels. `rag.py` implements TF-IDF + cosine similarity from
scratch using only the standard library (`re`, `math`, `collections`).
Nothing to compile, works anywhere Python runs.

It's the same underlying idea as embedding-based vector search (turn text
into vectors, rank by similarity) — just using word-overlap statistics
instead of a neural embedding model. For a small, well-scoped knowledge
base like this, it works well and is honestly a better way to *learn*
what retrieval is doing under the hood before you use a black-box library.

## What's new

**`knowledge/`** — three text files, your actual business knowledge:
- `services.txt` — what you offer and starting prices
- `hours_and_policies.txt` — hours, deposits, cancellation, delivery area
- `faq.txt` — common customer questions

Edit these directly with your real business info — no code changes needed.

**`rag.py`** — loads and chunks the `.txt` files (split by paragraph),
builds a TF-IDF index, and exposes `search_knowledge_base(query, top_k)`.

**`assistant.py`** — the old `get_price_info`/`get_business_hours` tools
are gone, replaced by one `search_knowledge_base` tool. The system prompt
now instructs Claude to always search before answering business questions,
rather than guessing.

`database.py` and `main.py` are unchanged from your memory upgrade.

## Test it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY="sk-ant-..."
uvicorn main:app --reload
```

```bash
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=do%20you%20handle%20outdoor%20weddings"
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=whats%20your%20cancellation%20policy"
curl "http://127.0.0.1:8000/message?phone_number=+15551111111&text=do%20you%20do%20wheelchair%20accessible%20setups"
```

You can also test the retrieval directly without the API:
```bash
python3 -c "from rag import search_knowledge_base; print(search_knowledge_base('cancellation policy'))"
```

## Good next exercises
- Add a `/admin/reload-knowledge` endpoint that rebuilds the index without
  restarting the server, so you can edit `knowledge/` files live
- Add source attribution — have Claude mention which doc an answer came
  from, useful for debugging
- Once you're comfortable, swap `rag.py`'s TF-IDF for real embeddings
  (e.g. Voyage AI, Anthropic's recommended embeddings partner) and
  compare retrieval quality — a great before/after to talk about in
  interviews
- Chunk smarter: right now it splits on blank lines; try smaller/overlapping
  chunks for longer documents

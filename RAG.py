"""
rag.py — lightweight retrieval-augmented generation, built from scratch
with the standard library only (no numpy/scikit-learn/sentence-transformers).
Chosen deliberately so it installs cleanly on Termux without compiling
anything.

How it works:
1. Load every .txt file in knowledge/, split into paragraph-sized chunks.
2. Build a TF-IDF vector for each chunk (term frequency x inverse
   document frequency — common words across all chunks matter less,
   rare/specific words matter more).
3. At query time, vectorize the query the same way and rank chunks by
   cosine similarity.

This is the same core idea as embedding-based vector search, just with
word-overlap statistics instead of a neural embedding model. Good enough
for a small, well-defined knowledge base like this one.
"""

import os
import re
import math
from collections import Counter

KNOWLEDGE_DIR = "knowledge"


def _tokenize(text: str):
    return re.findall(r"[a-z0-9]+", text.lower())


def _load_chunks():
    """Split each .txt file into paragraph chunks."""
    chunks = []  # list of {"source": filename, "text": chunk_text}
    if not os.path.isdir(KNOWLEDGE_DIR):
        return chunks

    for filename in sorted(os.listdir(KNOWLEDGE_DIR)):
        if not filename.endswith(".txt"):
            continue
        path = os.path.join(KNOWLEDGE_DIR, filename)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        for p in paragraphs:
            chunks.append({"source": filename, "text": p})

    return chunks


class KnowledgeBase:
    def __init__(self):
        self.chunks = _load_chunks()
        self._build_index()

    def _build_index(self):
        # tokenize every chunk
        self._tokenized = [_tokenize(c["text"]) for c in self.chunks]
        n_docs = len(self._tokenized)

        # document frequency: how many chunks contain each term
        df = Counter()
        for tokens in self._tokenized:
            for term in set(tokens):
                df[term] += 1

        self._idf = {
            term: math.log((n_docs + 1) / (freq + 1)) + 1
            for term, freq in df.items()
        }

        # precompute TF-IDF vector (as a dict) for each chunk
        self._chunk_vectors = [self._vectorize(tokens) for tokens in self._tokenized]
        self._chunk_norms = [self._norm(v) for v in self._chunk_vectors]

    def _vectorize(self, tokens):
        tf = Counter(tokens)
        return {term: count * self._idf.get(term, 0.0) for term, count in tf.items()}

    @staticmethod
    def _norm(vector):
        return math.sqrt(sum(v * v for v in vector.values())) or 1e-9

    @staticmethod
    def _dot(v1, v2):
        # iterate over the smaller dict for efficiency
        if len(v1) > len(v2):
            v1, v2 = v2, v1
        return sum(val * v2.get(term, 0.0) for term, val in v1.items())

    def search(self, query: str, top_k: int = 3):
        """Return the top_k most relevant chunks for the query."""
        if not self.chunks:
            return []

        query_tokens = _tokenize(query)
        query_vector = self._vectorize(query_tokens)
        query_norm = self._norm(query_vector)

        scored = []
        for i, chunk_vector in enumerate(self._chunk_vectors):
            similarity = self._dot(query_vector, chunk_vector) / (query_norm * self._chunk_norms[i])
            scored.append((similarity, i))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = []
        for similarity, i in scored[:top_k]:
            if similarity <= 0:
                continue
            results.append({
                "source": self.chunks[i]["source"],
                "text": self.chunks[i]["text"],
                "relevance": round(similarity, 3),
            })
        return results


# Built once at import time. Re-import or call .reload() if you edit the
# knowledge/ files while the server is running.
knowledge_base = KnowledgeBase()


def search_knowledge_base(query: str, top_k: int = 3):
    return knowledge_base.search(query, top_k=top_k)

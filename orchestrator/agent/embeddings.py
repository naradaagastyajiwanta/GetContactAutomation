"""Embedding utilities for semantic similarity search.

Provides functions to generate, encode, decode, and compare OpenAI
text embeddings. Used for semantic retrieval in knowledge base and
contact memory matching.

All functions are async-safe. Embedding generation calls the OpenAI
embeddings API (text-embedding-3-small by default — fast and cheap).
"""
from __future__ import annotations

import asyncio
import json
import math
import struct
from functools import partial
from typing import Sequence

from orchestrator.config import cfg, log
from orchestrator.llm import gateway

_EMBEDDING_MODEL = "text-embedding-3-small"
_EMBEDDING_DIM = 1536  # dimensions for text-embedding-3-small

# NOTE: embeddings always go to the real OpenAI API via gateway.embeddings_create
# — the chatgpt-proxy sidecar does not expose /v1/embeddings.


# ---------------------------------------------------------------------------
# Core API
# ---------------------------------------------------------------------------


async def get_embedding(text: str) -> list[float]:
    """Return a 1536-dim embedding vector for the given text.

    Strips whitespace and truncates very long inputs to ~8000 chars to stay
    within the model's token limit without extra tokenisation overhead.
    """
    text = text.strip()
    if not text:
        return [0.0] * _EMBEDDING_DIM
    # Rough character limit for text-embedding-3-small (8191 tokens ≈ 32k chars)
    if len(text) > 30_000:
        text = text[:30_000]

    try:
        response = await gateway.embeddings_create(
            model=_EMBEDDING_MODEL,
            input=text,
        )
        return response.data[0].embedding
    except Exception as e:
        log.warning("get_embedding failed: %s", e)
        return [0.0] * _EMBEDDING_DIM


def encode_embedding(vector: list[float]) -> bytes:
    """Pack a float list into a compact binary representation (SQLite BLOB)."""
    return struct.pack(f"{len(vector)}f", *vector)


def decode_embedding(blob: bytes) -> list[float]:
    """Unpack a binary BLOB back into a float list."""
    n = len(blob) // 4  # each float32 = 4 bytes
    return list(struct.unpack(f"{n}f", blob))


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Return cosine similarity between two vectors (range −1 to 1)."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# ---------------------------------------------------------------------------
# Batch builder (called by scheduler job)
# ---------------------------------------------------------------------------


async def build_missing_embeddings() -> dict:
    """Generate and store embeddings for any un-embedded rows.

    Covers:
    - knowledge_items (content column → embedding column)
    - lessons (insight + recommended_strategy → embedding column)

    Returns a summary dict with counts.
    """
    from orchestrator.db import get_db

    built_ki = 0
    built_ls = 0

    try:
        async with get_db() as db:
            # ---- knowledge_items ----
            cursor = await db.execute(
                "SELECT id, content FROM knowledge_items "
                "WHERE embedding IS NULL AND is_active = 1 LIMIT 50"
            )
            ki_rows = await cursor.fetchall()

        for row in ki_rows:
            try:
                vec = await get_embedding(row[1] or "")
                blob = encode_embedding(vec)
                async with get_db() as db:
                    await db.execute(
                        "UPDATE knowledge_items SET embedding = ? WHERE id = ?",
                        (blob, row[0]),
                    )
                    await db.commit()
                built_ki += 1
            except Exception as e:
                log.warning("build_missing_embeddings: ki %d failed: %s", row[0], e)

        async with get_db() as db:
            # ---- lessons ----
            cursor = await db.execute(
                "SELECT id, insight, recommended_strategy FROM lessons "
                "WHERE embedding IS NULL AND is_active = 1 LIMIT 50"
            )
            ls_rows = await cursor.fetchall()

        for row in ls_rows:
            try:
                combined = f"{row[1] or ''} {row[2] or ''}".strip()
                vec = await get_embedding(combined)
                blob = encode_embedding(vec)
                async with get_db() as db:
                    await db.execute(
                        "UPDATE lessons SET embedding = ? WHERE id = ?",
                        (blob, row[0]),
                    )
                    await db.commit()
                built_ls += 1
            except Exception as e:
                log.warning("build_missing_embeddings: lesson %d failed: %s", row[0], e)

    except Exception as e:
        log.error("build_missing_embeddings: outer error: %s", e)

    log.info(
        "build_missing_embeddings: built %d knowledge_item embeddings, %d lesson embeddings",
        built_ki, built_ls,
    )
    return {"knowledge_items": built_ki, "lessons": built_ls}


# ---------------------------------------------------------------------------
# Semantic retrieval helpers
# ---------------------------------------------------------------------------


async def semantic_match_knowledge_items(
    chatbot_type: str,
    query_text: str,
    top_k: int = 5,
    min_similarity: float = 0.70,
) -> list[dict]:
    """Return the top-k knowledge_items most semantically similar to query_text.

    Falls back to empty list if no embeddings exist yet.
    """
    from orchestrator.db import get_db, _rows_to_dicts

    query_vec = await get_embedding(query_text)

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, title, content, situation_tags, embedding "
            "FROM knowledge_items "
            "WHERE is_active = 1 AND chatbot_type = ? AND embedding IS NOT NULL",
            (chatbot_type,),
        )
        rows = await cursor.fetchall()

    scored = []
    for row in rows:
        blob = row[4]
        if not blob:
            continue
        vec = decode_embedding(blob)
        sim = cosine_similarity(query_vec, vec)
        if sim >= min_similarity:
            scored.append((sim, row))

    scored.sort(key=lambda x: x[0], reverse=True)
    results = []
    for sim, row in scored[:top_k]:
        results.append({
            "id": row[0],
            "title": row[1],
            "content": row[2],
            "situation_tags": row[3],
            "similarity": round(sim, 4),
        })
    return results

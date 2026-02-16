"""SQLite BLOB + NumPy cosine similarity vector store for agent memories.

Scalability note: search_memories loads all embeddings for the agent into memory
and computes cosine similarity with NumPy. This is fine for <10k memories per agent.
For larger scale, consider SQLite FTS5 for coarse filtering before vector ranking.
"""

import logging

import httpx
import numpy as np
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..models import Memory

logger = logging.getLogger(__name__)

_client: httpx.AsyncClient | None = None


async def init_vector_store() -> None:
    """Initialize the embedding API client."""
    global _client
    if not settings.embedding_api_key:
        logger.warning("EMBEDDING_API_KEY not configured — vector search will be unavailable")
    _client = httpx.AsyncClient(
        base_url=settings.embedding_api_base,
        headers={"Authorization": f"Bearer {settings.embedding_api_key}"},
        timeout=30.0,
    )
    logger.info("Vector store initialized (embedding API: %s, model: %s)",
                settings.embedding_api_base, settings.embedding_model)


async def close_vector_store() -> None:
    """Shutdown the embedding API client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
        logger.info("Vector store client closed")


async def embed(text: str) -> bytes:
    """Call embedding API and return float32 bytes."""
    if _client is None:
        raise RuntimeError("vector_store not initialized. Call init_vector_store() first.")
    resp = await _client.post("/embeddings", json={
        "model": settings.embedding_model,
        "input": text,
        "encoding_format": "float",
    })
    resp.raise_for_status()
    data = resp.json()
    if not data.get("data") or not data["data"][0].get("embedding"):
        raise ValueError(f"Unexpected embedding API response: {list(data.keys())}")
    vec = data["data"][0]["embedding"]
    blob = np.array(vec, dtype=np.float32).tobytes()
    expected_size = settings.embedding_dim * 4
    if len(blob) != expected_size:
        raise ValueError(f"Embedding dimension mismatch: got {len(blob) // 4}, expected {settings.embedding_dim}")
    return blob


async def upsert_memory(
    memory_id: int, agent_id: int, text: str, db: AsyncSession
) -> None:
    """Generate embedding and store it in the Memory row."""
    if not text or not text.strip():
        raise ValueError("Cannot embed empty or blank text")
    blob = await embed(text)
    mem = await db.get(Memory, memory_id)
    if mem is None:
        raise ValueError(f"Memory {memory_id} not found in database")
    mem.embedding = blob


async def search_memories(
    query: str, agent_id: int, top_k: int = 5, db: AsyncSession | None = None
) -> list[dict]:
    """Search memories by cosine similarity."""
    if not query or not query.strip():
        return []
    if db is None:
        return []

    query_blob = await embed(query)
    query_vec = np.frombuffer(query_blob, dtype=np.float32)

    # P0: guard against zero-norm query vector (e.g. API returned all zeros)
    query_norm = np.linalg.norm(query_vec)
    if query_norm < 1e-8:
        logger.warning("Query embedding has near-zero norm, returning empty results")
        return []

    stmt = select(Memory).where(
        Memory.embedding.isnot(None),
        (Memory.agent_id == agent_id) | (Memory.agent_id.is_(None))
    )
    rows = (await db.execute(stmt)).scalars().all()
    if not rows:
        return []

    vecs = np.array([np.frombuffer(r.embedding, dtype=np.float32) for r in rows])
    row_norms = np.linalg.norm(vecs, axis=1)
    norms = row_norms * query_norm + 1e-8
    sims = vecs @ query_vec / norms
    top_k = max(1, min(top_k, len(rows)))
    top_idx = np.argsort(sims)[-top_k:][::-1]

    return [
        {"memory_id": rows[i].id, "text": rows[i].content, "_distance": float(1 - sims[i])}
        for i in top_idx
    ]


async def delete_memory(memory_id: int) -> None:
    """No-op: SQLite cascade handles deletion."""
    pass

"""LanceDB vector store for agent memories."""

import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_db = None
_model = None
_table = None

VECTOR_DIM = 512
TABLE_NAME = "memories"


def _ensure_initialized():
    if _table is None or _model is None:
        raise RuntimeError("vector_store not initialized. Call init_vector_store() first.")


def _build_schema():
    import pyarrow as pa
    return pa.schema([
        pa.field("memory_id", pa.int64()),
        pa.field("agent_id", pa.int64()),
        pa.field("text", pa.utf8()),
        pa.field("memory_type", pa.utf8()),
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        pa.field("created_at", pa.utf8()),
    ])


async def init_vector_store(lancedb_path: str) -> None:
    global _db, _model, _table
    import lancedb as _lancedb
    from sentence_transformers import SentenceTransformer
    from ..core.config import settings

    _db = await asyncio.to_thread(_lancedb.connect, lancedb_path)
    _model = await asyncio.to_thread(
        SentenceTransformer, settings.embedding_model_path
    )
    table_names = await asyncio.to_thread(_db.table_names)
    if TABLE_NAME in table_names:
        _table = await asyncio.to_thread(_db.open_table, TABLE_NAME)
    else:
        _table = await asyncio.to_thread(_db.create_table, TABLE_NAME, schema=_build_schema())


def embed(text: str) -> list[float]:
    _ensure_initialized()
    return _model.encode(text, normalize_embeddings=True).tolist()


def _upsert_sync(row: dict, memory_id: int) -> None:
    """Sync helper for upsert — runs in thread pool."""
    if not isinstance(memory_id, int):
        raise TypeError(f"memory_id must be int, got {type(memory_id)}")
    try:
        _table.delete(f"memory_id = {memory_id}")
    except Exception:
        logger.debug("No existing row for memory_id=%d, inserting fresh", memory_id)
    _table.add([row])


async def upsert_memory(
    memory_id: int, agent_id: int, text: str, memory_type: str
) -> None:
    _ensure_initialized()
    if not text or not text.strip():
        raise ValueError("Cannot embed empty or blank text")
    vec = await asyncio.to_thread(embed, text)
    row = {
        "memory_id": memory_id,
        "agent_id": agent_id,
        "text": text,
        "memory_type": memory_type,
        "vector": vec,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await asyncio.to_thread(_upsert_sync, row, memory_id)


def _search_sync(vec: list[float], agent_id: int, top_k: int) -> list[dict]:
    """Sync helper for search — runs in thread pool."""
    if not isinstance(agent_id, int):
        raise TypeError(f"agent_id must be int, got {type(agent_id)}")
    return (
        _table.search(vec)
        .where(f"(agent_id = {agent_id}) OR (agent_id = -1)", prefilter=True)
        .limit(top_k)
        .to_list()
    )


async def search_memories(
    query: str, agent_id: int, top_k: int = 5
) -> list[dict]:
    _ensure_initialized()
    if not query or not query.strip():
        return []
    vec = await asyncio.to_thread(embed, query)
    return await asyncio.to_thread(_search_sync, vec, agent_id, top_k)


async def delete_memory(memory_id: int) -> None:
    _ensure_initialized()
    if not isinstance(memory_id, int):
        raise TypeError(f"memory_id must be int, got {type(memory_id)}")
    await asyncio.to_thread(_table.delete, f"memory_id = {memory_id}")

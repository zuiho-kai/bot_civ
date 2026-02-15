"""LanceDB vector store for agent memories."""

import asyncio
from datetime import datetime, timezone

import lancedb
import pyarrow as pa
from sentence_transformers import SentenceTransformer

_db: lancedb.DBConnection | None = None
_model: SentenceTransformer | None = None
_table: lancedb.table.Table | None = None

VECTOR_DIM = 512
TABLE_NAME = "memories"

_schema = pa.schema([
    pa.field("memory_id", pa.int64()),
    pa.field("agent_id", pa.int64()),
    pa.field("text", pa.utf8()),
    pa.field("memory_type", pa.utf8()),
    pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
    pa.field("created_at", pa.utf8()),
])


async def init_vector_store(lancedb_path: str) -> None:
    global _db, _model, _table
    _db = lancedb.connect(lancedb_path)
    _model = await asyncio.to_thread(
        SentenceTransformer, "BAAI/bge-small-zh-v1.5"
    )
    if TABLE_NAME in _db.table_names():
        _table = _db.open_table(TABLE_NAME)
    else:
        _table = _db.create_table(TABLE_NAME, schema=_schema)


def embed(text: str) -> list[float]:
    return _model.encode(text, normalize_embeddings=True).tolist()


async def upsert_memory(
    memory_id: int, agent_id: int, text: str, memory_type: str
) -> None:
    vec = await asyncio.to_thread(embed, text)
    row = {
        "memory_id": memory_id,
        "agent_id": agent_id,
        "text": text,
        "memory_type": memory_type,
        "vector": vec,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    # delete old row if exists, then add
    try:
        _table.delete(f"memory_id = {memory_id}")
    except Exception:
        pass
    _table.add([row])


async def search_memories(
    query: str, agent_id: int, top_k: int = 5
) -> list[dict]:
    vec = await asyncio.to_thread(embed, query)
    results = (
        _table.search(vec)
        .where(f"(agent_id = {agent_id}) OR (agent_id = -1)", prefilter=True)
        .limit(top_k)
        .to_list()
    )
    return results


async def delete_memory(memory_id: int) -> None:
    _table.delete(f"memory_id = {memory_id}")

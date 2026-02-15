import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import Memory, MemoryType
from . import vector_store

logger = logging.getLogger(__name__)

SHORT_MEMORY_TTL_DAYS = 7
PROMOTE_THRESHOLD = 5


class MemoryService:

    async def save_memory(
        self, agent_id: int | None, content: str, memory_type: MemoryType, db: AsyncSession
    ) -> Memory:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=SHORT_MEMORY_TTL_DAYS) if memory_type == MemoryType.SHORT else None
        db_agent_id = None if memory_type == MemoryType.PUBLIC else agent_id

        memory = Memory(
            agent_id=db_agent_id,
            memory_type=memory_type,
            content=content,
            expires_at=expires_at,
        )
        db.add(memory)
        await db.commit()
        await db.refresh(memory)

        vec_agent_id = -1 if memory_type == MemoryType.PUBLIC else agent_id
        try:
            await vector_store.upsert_memory(
                memory.id, vec_agent_id, content, memory_type
            )
        except Exception as e:
            logger.error("Vector upsert failed for memory %d, deleting SQLite row: %s", memory.id, e)
            await db.delete(memory)
            await db.commit()
            raise

        return memory

    async def search(
        self, agent_id: int, query: str, top_k: int = 5, db: AsyncSession | None = None
    ) -> list[Memory] | list[dict]:
        results = await vector_store.search_memories(query, agent_id, top_k)
        if not results:
            return []

        if db is None:
            return results

        memory_ids = [r["memory_id"] for r in results]
        stmt = select(Memory).where(Memory.id.in_(memory_ids))
        rows = (await db.execute(stmt)).scalars().all()

        if len(rows) != len(memory_ids):
            found_ids = {m.id for m in rows}
            orphans = [mid for mid in memory_ids if mid not in found_ids]
            logger.warning("Vector/SQLite mismatch: orphan memory_ids=%s", orphans)

        for mem in rows:
            mem.access_count += 1
            if mem.memory_type == MemoryType.SHORT and mem.access_count >= PROMOTE_THRESHOLD:
                mem.memory_type = MemoryType.LONG
                mem.expires_at = None

        await db.commit()

        # Preserve vector similarity ranking
        row_map = {m.id: m for m in rows}
        return [row_map[mid] for mid in memory_ids if mid in row_map]

    async def cleanup_expired(self, db: AsyncSession) -> int:
        now = datetime.now(timezone.utc)
        stmt = select(Memory).where(
            Memory.memory_type == MemoryType.SHORT,
            Memory.expires_at < now,
        )
        expired = (await db.execute(stmt)).scalars().all()

        cleaned = 0
        for mem in expired:
            try:
                await vector_store.delete_memory(mem.id)
            except Exception as e:
                logger.error("Vector delete failed for memory %d: %s", mem.id, e)
                continue
            await db.delete(mem)
            cleaned += 1

        await db.commit()
        return cleaned


memory_service = MemoryService()

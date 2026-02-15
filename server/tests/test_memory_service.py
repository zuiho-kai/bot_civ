from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from app.models import Memory, MemoryType
from app.services.memory_service import memory_service

VECTOR_STORE = "app.services.memory_service.vector_store"


@pytest.mark.asyncio
async def test_save_short_memory(db):
    with patch(f"{VECTOR_STORE}.upsert_memory", new_callable=AsyncMock) as mock_upsert:
        mem = await memory_service.save_memory(1, "hello world", MemoryType.SHORT, db)

    assert mem.id is not None
    assert mem.agent_id == 1
    assert mem.memory_type == MemoryType.SHORT
    assert mem.content == "hello world"
    assert mem.expires_at is not None
    delta = mem.expires_at - datetime.now(timezone.utc).replace(tzinfo=None)
    assert timedelta(days=6) < delta < timedelta(days=8)
    mock_upsert.assert_awaited_once_with(mem.id, 1, "hello world", MemoryType.SHORT)


@pytest.mark.asyncio
async def test_save_long_memory(db):
    with patch(f"{VECTOR_STORE}.upsert_memory", new_callable=AsyncMock) as mock_upsert:
        mem = await memory_service.save_memory(1, "important fact", MemoryType.LONG, db)

    assert mem.memory_type == MemoryType.LONG
    assert mem.expires_at is None
    mock_upsert.assert_awaited_once_with(mem.id, 1, "important fact", MemoryType.LONG)


@pytest.mark.asyncio
async def test_save_public_memory(db):
    with patch(f"{VECTOR_STORE}.upsert_memory", new_callable=AsyncMock) as mock_upsert:
        mem = await memory_service.save_memory(1, "public info", MemoryType.PUBLIC, db)

    assert mem.agent_id is None
    assert mem.expires_at is None
    mock_upsert.assert_awaited_once_with(mem.id, -1, "public info", MemoryType.PUBLIC)


@pytest.mark.asyncio
async def test_search_increments_access_count(db):
    mem = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="test",
                 expires_at=datetime.now(timezone.utc) + timedelta(days=7), access_count=0)
    db.add(mem)
    await db.commit()
    await db.refresh(mem)

    mock_results = [{"memory_id": mem.id, "text": "test", "_distance": 0.1}]
    with patch(f"{VECTOR_STORE}.search_memories", new_callable=AsyncMock, return_value=mock_results):
        results = await memory_service.search(1, "test", db=db)

    assert len(results) == 1
    assert results[0].access_count == 1


@pytest.mark.asyncio
async def test_promote_short_to_long(db):
    mem = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="popular",
                 expires_at=datetime.now(timezone.utc) + timedelta(days=7), access_count=4)
    db.add(mem)
    await db.commit()
    await db.refresh(mem)

    mock_results = [{"memory_id": mem.id, "text": "popular", "_distance": 0.1}]
    with patch(f"{VECTOR_STORE}.search_memories", new_callable=AsyncMock, return_value=mock_results):
        results = await memory_service.search(1, "popular", db=db)

    assert results[0].access_count == 5
    assert results[0].memory_type == MemoryType.LONG
    assert results[0].expires_at is None


@pytest.mark.asyncio
async def test_cleanup_expired(db):
    expired = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="old",
                     expires_at=datetime.now(timezone.utc) - timedelta(days=1), access_count=0)
    alive = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="fresh",
                   expires_at=datetime.now(timezone.utc) + timedelta(days=5), access_count=0)
    db.add_all([expired, alive])
    await db.commit()
    await db.refresh(expired)
    await db.refresh(alive)

    with patch(f"{VECTOR_STORE}.delete_memory", new_callable=AsyncMock) as mock_delete:
        count = await memory_service.cleanup_expired(db)

    assert count == 1
    mock_delete.assert_awaited_once_with(expired.id)
    remaining = await db.get(Memory, alive.id)
    assert remaining is not None

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Agent, Memory, MemoryType
from app.services.scheduler import daily_grant, daily_memory_cleanup, DAILY_CREDIT_GRANT, HUMAN_ID
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.database import Base


@pytest_asyncio.fixture
async def db_and_maker():
    """Provide both a session and a session maker for scheduler functions."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as session:
        yield session, maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_daily_grant_adds_credits(db_and_maker):
    db, maker = db_and_maker
    # Create Human (id=0) and two agents
    db.add(Agent(id=0, name="Human", persona="人类", model="none", credits=0))
    db.add(Agent(id=1, name="Alice", persona="test", model="test", credits=50))
    db.add(Agent(id=2, name="Bob", persona="test", model="test", credits=20))
    await db.commit()

    count = await daily_grant(db_session_maker=maker)
    assert count == 2

    # Verify credits updated
    async with maker() as check_db:
        human = await check_db.get(Agent, 0)
        alice = await check_db.get(Agent, 1)
        bob = await check_db.get(Agent, 2)
        assert human.credits == 0  # Human not affected
        assert alice.credits == 50 + DAILY_CREDIT_GRANT
        assert bob.credits == 20 + DAILY_CREDIT_GRANT


@pytest.mark.asyncio
async def test_daily_grant_no_agents(db_and_maker):
    db, maker = db_and_maker
    db.add(Agent(id=0, name="Human", persona="人类", model="none", credits=0))
    await db.commit()

    count = await daily_grant(db_session_maker=maker)
    assert count == 0


@pytest.mark.asyncio
async def test_daily_memory_cleanup(db_and_maker):
    db, maker = db_and_maker
    db.add(Agent(id=1, name="Alice", persona="test", model="test"))
    await db.commit()

    expired = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="old",
                     expires_at=datetime.now(timezone.utc) - timedelta(days=1))
    alive = Memory(agent_id=1, memory_type=MemoryType.SHORT, content="fresh",
                   expires_at=datetime.now(timezone.utc) + timedelta(days=5))
    db.add_all([expired, alive])
    await db.commit()

    with patch("app.services.memory_service.vector_store.delete_memory", new_callable=AsyncMock):
        count = await daily_memory_cleanup(db_session_maker=maker)

    assert count == 1

import pytest
from sqlalchemy import select

from app.models import Agent, LLMUsage


@pytest.mark.asyncio
async def test_llm_usage_create_and_persist(db):
    """LLMUsage model can be created and persisted."""
    agent = Agent(id=1, name="test_agent", persona="test")
    db.add(agent)
    await db.commit()

    record = LLMUsage(
        model="gpt-4o-mini",
        agent_id=1,
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=320,
    )
    db.add(record)
    await db.commit()

    result = await db.execute(select(LLMUsage).where(LLMUsage.agent_id == 1))
    row = result.scalar_one()
    assert row.model == "gpt-4o-mini"
    assert row.prompt_tokens == 100
    assert row.completion_tokens == 50
    assert row.total_tokens == 150
    assert row.latency_ms == 320
    assert row.cost == 0.0


@pytest.mark.asyncio
async def test_llm_usage_defaults(db):
    """LLMUsage defaults are applied correctly."""
    record = LLMUsage(model="test-model", agent_id=None)
    db.add(record)
    await db.commit()

    result = await db.execute(select(LLMUsage))
    row = result.scalar_one()
    assert row.prompt_tokens == 0
    assert row.completion_tokens == 0
    assert row.total_tokens == 0
    assert row.cost == 0.0
    assert row.latency_ms == 0
    assert row.agent_id is None


@pytest.mark.asyncio
async def test_llm_usage_multiple_records(db):
    """Multiple LLMUsage records can be stored and queried."""
    agent = Agent(id=1, name="test_agent", persona="test")
    db.add(agent)
    await db.commit()

    for i in range(3):
        record = LLMUsage(
            model=f"model-{i}",
            agent_id=1,
            prompt_tokens=10 * (i + 1),
            completion_tokens=5 * (i + 1),
            total_tokens=15 * (i + 1),
            latency_ms=100 * (i + 1),
        )
        db.add(record)
    await db.commit()

    result = await db.execute(select(LLMUsage).where(LLMUsage.agent_id == 1))
    rows = result.scalars().all()
    assert len(rows) == 3


@pytest.mark.asyncio
async def test_vector_store_imports():
    """vector_store module can be imported without errors."""
    from app.services import vector_store
    assert hasattr(vector_store, "init_vector_store")
    assert hasattr(vector_store, "upsert_memory")
    assert hasattr(vector_store, "search_memories")
    assert hasattr(vector_store, "delete_memory")
    assert hasattr(vector_store, "embed")
    assert hasattr(vector_store, "close_vector_store")

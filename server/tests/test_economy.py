import pytest
from datetime import date, timedelta

from app.models import Agent
from app.services.economy_service import EconomyService, HUMAN_ID


@pytest.fixture
def svc():
    return EconomyService()


async def _make_agent(db, *, id=1, credits=100, daily_free_quota=10,
                      quota_used_today=0, quota_reset_date=None) -> Agent:
    agent = Agent(
        id=id,
        name=f"agent_{id}",
        persona="test persona",
        credits=credits,
        daily_free_quota=daily_free_quota,
        quota_used_today=quota_used_today,
        quota_reset_date=quota_reset_date or date.today(),
    )
    db.add(agent)
    await db.commit()
    return agent


# --- check_quota ---

@pytest.mark.asyncio
async def test_human_always_allowed(svc, db):
    result = await svc.check_quota(HUMAN_ID, "chat", db)
    assert result.allowed is True
    assert result.reason == "human"


@pytest.mark.asyncio
async def test_work_message_always_free(svc, db):
    await _make_agent(db, id=1, credits=0, daily_free_quota=0, quota_used_today=0)
    result = await svc.check_quota(1, "work", db)
    assert result.allowed is True
    assert result.reason == "work is free"


@pytest.mark.asyncio
async def test_agent_within_free_quota(svc, db):
    await _make_agent(db, id=1, credits=0, daily_free_quota=10, quota_used_today=5)
    result = await svc.check_quota(1, "chat", db)
    assert result.allowed is True
    assert result.reason == "free quota available"


@pytest.mark.asyncio
async def test_agent_exhausted_free_quota_has_credits(svc, db):
    await _make_agent(db, id=1, credits=50, daily_free_quota=10, quota_used_today=10)
    result = await svc.check_quota(1, "chat", db)
    assert result.allowed is True
    assert result.reason == "credits available"


@pytest.mark.asyncio
async def test_agent_no_quota_no_credits_denied(svc, db):
    await _make_agent(db, id=1, credits=0, daily_free_quota=10, quota_used_today=10)
    result = await svc.check_quota(1, "chat", db)
    assert result.allowed is False
    assert result.reason == "no quota or credits left"


@pytest.mark.asyncio
async def test_agent_not_found(svc, db):
    result = await svc.check_quota(999, "chat", db)
    assert result.allowed is False
    assert result.reason == "agent not found"


@pytest.mark.asyncio
async def test_lazy_daily_reset(svc, db):
    yesterday = date.today() - timedelta(days=1)
    await _make_agent(db, id=1, credits=0, daily_free_quota=10,
                      quota_used_today=10, quota_reset_date=yesterday)
    result = await svc.check_quota(1, "chat", db)
    assert result.allowed is True
    assert result.reason == "free quota available"
    # Verify the reset happened
    agent = await db.get(Agent, 1)
    assert agent.quota_used_today == 0
    assert agent.quota_reset_date == date.today()


# --- deduct_quota ---

@pytest.mark.asyncio
async def test_deduct_within_free_quota(svc, db):
    await _make_agent(db, id=1, credits=100, daily_free_quota=10, quota_used_today=3)
    await svc.deduct_quota(1, db)
    agent = await db.get(Agent, 1)
    assert agent.quota_used_today == 4
    assert agent.credits == 100  # credits untouched


@pytest.mark.asyncio
async def test_deduct_beyond_free_quota(svc, db):
    await _make_agent(db, id=1, credits=50, daily_free_quota=10, quota_used_today=10)
    await svc.deduct_quota(1, db)
    agent = await db.get(Agent, 1)
    assert agent.credits == 49


@pytest.mark.asyncio
async def test_deduct_human_noop(svc, db):
    # Should not raise
    await svc.deduct_quota(HUMAN_ID, db)


@pytest.mark.asyncio
async def test_deduct_nonexistent_agent_noop(svc, db):
    await svc.deduct_quota(999, db)


# --- transfer_credits ---

@pytest.mark.asyncio
async def test_transfer_credits_success(svc, db):
    await _make_agent(db, id=1, credits=100)
    await _make_agent(db, id=2, credits=50)
    result = await svc.transfer_credits(1, 2, 30, db)
    assert result is True
    sender = await db.get(Agent, 1)
    receiver = await db.get(Agent, 2)
    assert sender.credits == 70
    assert receiver.credits == 80


@pytest.mark.asyncio
async def test_transfer_insufficient_balance(svc, db):
    await _make_agent(db, id=1, credits=10)
    await _make_agent(db, id=2, credits=50)
    result = await svc.transfer_credits(1, 2, 20, db)
    assert result is False
    sender = await db.get(Agent, 1)
    assert sender.credits == 10  # unchanged


@pytest.mark.asyncio
async def test_transfer_invalid_agent(svc, db):
    await _make_agent(db, id=1, credits=100)
    result = await svc.transfer_credits(1, 999, 10, db)
    assert result is False


@pytest.mark.asyncio
async def test_transfer_negative_amount(svc, db):
    await _make_agent(db, id=1, credits=100)
    await _make_agent(db, id=2, credits=50)
    result = await svc.transfer_credits(1, 2, -5, db)
    assert result is False


@pytest.mark.asyncio
async def test_transfer_zero_amount(svc, db):
    await _make_agent(db, id=1, credits=100)
    await _make_agent(db, id=2, credits=50)
    result = await svc.transfer_credits(1, 2, 0, db)
    assert result is False


# --- get_balance ---

@pytest.mark.asyncio
async def test_get_balance(svc, db):
    await _make_agent(db, id=1, credits=80, daily_free_quota=10, quota_used_today=3)
    balance = await svc.get_balance(1, db)
    assert balance == {
        "credits": 80,
        "daily_free_quota": 10,
        "quota_used_today": 3,
        "free_remaining": 7,
    }


@pytest.mark.asyncio
async def test_get_balance_nonexistent(svc, db):
    result = await svc.get_balance(999, db)
    assert result is None

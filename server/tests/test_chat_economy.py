"""Tests for economy integration in chat wakeup flow."""

import pytest
import pytest_asyncio
from datetime import date
from unittest.mock import patch, AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from app.core.database import Base
from app.models import Agent, Message
from app.services.economy_service import CanSpeakResult


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_maker() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def setup_data(db):
    """Create test agent and message in the DB."""
    agent = Agent(
        id=1,
        name="TestBot",
        persona="test",
        credits=100,
        daily_free_quota=10,
        quota_used_today=0,
        quota_reset_date=date.today(),
    )
    # Human agent (id=0) needed for the message foreign key
    human = Agent(id=0, name="Human", persona="human", credits=0, daily_free_quota=0)
    db.add(human)
    db.add(agent)
    await db.commit()

    msg = Message(id=1, agent_id=0, sender_type="human", message_type="chat", content="hello")
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return agent, msg


def _make_context_manager(session):
    """Create an async context manager that yields the given session."""
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=session)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_wakeup_with_quota_allows_reply(db, setup_data):
    """Agent has free quota -> generate_reply called -> deduct_quota called."""
    agent, msg = setup_data

    mock_runner = MagicMock()
    mock_runner.generate_reply = AsyncMock(return_value="Hi there!")

    with (
        patch("app.api.chat.async_session", return_value=_make_context_manager(db)),
        patch("app.api.chat.wakeup_service") as mock_wakeup,
        patch("app.api.chat.runner_manager") as mock_rm,
        patch("app.api.chat.send_agent_message", new_callable=AsyncMock) as mock_send,
        patch("app.api.chat.economy_service") as mock_econ,
        patch("app.api.chat.bot_connections", {}),
        patch("app.api.chat.human_connections", {}),
    ):
        mock_wakeup.process = AsyncMock(return_value=[1])
        mock_rm.get_or_create = MagicMock(return_value=mock_runner)
        mock_econ.check_quota = AsyncMock(
            return_value=CanSpeakResult(allowed=True, reason="free quota available")
        )
        mock_econ.deduct_quota = AsyncMock()

        from app.api.chat import handle_wakeup

        await handle_wakeup(msg)

        mock_econ.check_quota.assert_awaited_once_with(1, "chat", db)
        mock_runner.generate_reply.assert_awaited_once()
        mock_send.assert_awaited_once_with(agent.id, agent.name, "Hi there!")
        mock_econ.deduct_quota.assert_awaited_once_with(1, db)


@pytest.mark.asyncio
async def test_wakeup_no_quota_skips_reply(db, setup_data):
    """Agent has no quota/credits -> generate_reply NOT called."""
    _agent, msg = setup_data

    mock_runner = MagicMock()
    mock_runner.generate_reply = AsyncMock(return_value="should not happen")

    with (
        patch("app.api.chat.async_session", return_value=_make_context_manager(db)),
        patch("app.api.chat.wakeup_service") as mock_wakeup,
        patch("app.api.chat.runner_manager") as mock_rm,
        patch("app.api.chat.send_agent_message", new_callable=AsyncMock) as mock_send,
        patch("app.api.chat.economy_service") as mock_econ,
        patch("app.api.chat.bot_connections", {}),
        patch("app.api.chat.human_connections", {}),
    ):
        mock_wakeup.process = AsyncMock(return_value=[1])
        mock_rm.get_or_create = MagicMock(return_value=mock_runner)
        mock_econ.check_quota = AsyncMock(
            return_value=CanSpeakResult(allowed=False, reason="no quota or credits left")
        )
        mock_econ.deduct_quota = AsyncMock()

        from app.api.chat import handle_wakeup

        await handle_wakeup(msg)

        mock_econ.check_quota.assert_awaited_once_with(1, "chat", db)
        mock_runner.generate_reply.assert_not_awaited()
        mock_send.assert_not_awaited()
        mock_econ.deduct_quota.assert_not_awaited()


@pytest.mark.asyncio
async def test_deduct_after_successful_reply(db, setup_data):
    """Verify deduct_quota is called after send_agent_message, not before."""
    agent, msg = setup_data

    call_order = []

    async def track_send(*args, **kwargs):
        call_order.append("send")

    async def track_deduct(*args, **kwargs):
        call_order.append("deduct")

    mock_runner = MagicMock()
    mock_runner.generate_reply = AsyncMock(return_value="reply text")

    with (
        patch("app.api.chat.async_session", return_value=_make_context_manager(db)),
        patch("app.api.chat.wakeup_service") as mock_wakeup,
        patch("app.api.chat.runner_manager") as mock_rm,
        patch("app.api.chat.send_agent_message", side_effect=track_send),
        patch("app.api.chat.economy_service") as mock_econ,
        patch("app.api.chat.bot_connections", {}),
        patch("app.api.chat.human_connections", {}),
    ):
        mock_wakeup.process = AsyncMock(return_value=[1])
        mock_rm.get_or_create = MagicMock(return_value=mock_runner)
        mock_econ.check_quota = AsyncMock(
            return_value=CanSpeakResult(allowed=True, reason="free quota available")
        )
        mock_econ.deduct_quota = AsyncMock(side_effect=track_deduct)

        from app.api.chat import handle_wakeup

        await handle_wakeup(msg)

        assert call_order == ["send", "deduct"], f"Expected send before deduct, got: {call_order}"

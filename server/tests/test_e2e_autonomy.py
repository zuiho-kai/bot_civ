"""M4 E2E tests: autonomy engine — tick → decisions → state changes → WebSocket events."""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from starlette.testclient import TestClient

from app.core.database import Base, engine, async_session
from app.models import Agent, Job, VirtualItem

pytestmark = pytest.mark.asyncio

# --- Mock LLM 决策 ---

MOCK_DECISIONS_CHECKIN = json.dumps([
    {"agent_id": 1, "action": "checkin", "params": {}, "reason": "早上该上班了"},
])

MOCK_DECISIONS_PURCHASE = json.dumps([
    {"agent_id": 1, "action": "purchase", "params": {"item_id": 1}, "reason": "想买个金框"},
])

MOCK_DECISIONS_REST = json.dumps([
    {"agent_id": 1, "action": "rest", "params": {}, "reason": "今天累了"},
])

MOCK_DECISIONS_MIXED = json.dumps([
    {"agent_id": 1, "action": "checkin", "params": {}, "reason": "去上班"},
    {"agent_id": 2, "action": "rest", "params": {}, "reason": "休息一下"},
])

MOCK_DECISIONS_INVALID_JSON = "not valid json at all"


def _mock_llm(reply_text: str):
    """返回 resolve_model + AsyncOpenAI 的 patch，使 LLM 返回指定文本。"""
    mock_choice = MagicMock()
    mock_choice.message.content = reply_text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 100
    mock_response.usage.completion_tokens = 50
    mock_response.usage.total_tokens = 150

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    return (
        patch("app.services.autonomy_service.resolve_model",
              return_value=("http://fake", "sk-fake", "test-model")),
        patch("app.services.autonomy_service.AsyncOpenAI",
              return_value=mock_client),
    )


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables + seed, tear down after each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
        db.add(Agent(id=1, name="Alice", persona="乐观的程序员", model="test", credits=0))
        db.add(Agent(id=2, name="Bob", persona="沉稳的架构师", model="test", credits=50))
        db.add(Job(id=1, title="矿工", description="挖矿", daily_reward=10, max_workers=5))
        db.add(VirtualItem(id=1, name="金框", item_type="avatar_frame", price=8, description="test"))
        await db.commit()

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------- E1: autonomy tick — checkin → credits 增加 ----------

async def test_e2e_autonomy_checkin(client: AsyncClient):
    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_CHECKIN)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    # 验证 Alice credits 增加
    r = await client.get("/api/agents/1")
    assert r.status_code == 200
    assert r.json()["credits"] == 10  # 0 + daily_reward


# ---------- E2: autonomy tick — purchase → credits 减少 + 物品出现 ----------

async def test_e2e_autonomy_purchase(client: AsyncClient):
    # 先给 Alice 加钱
    async with async_session() as db:
        agent = await db.get(Agent, 1)
        agent.credits = 100
        await db.commit()

    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_PURCHASE)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200

    # 验证 credits 减少
    r = await client.get("/api/agents/1")
    assert r.json()["credits"] == 92  # 100 - 8

    # 验证物品出现
    r = await client.get("/api/shop/agents/1/items")
    items = r.json()
    assert len(items) == 1
    assert items[0]["item_id"] == 1


# ---------- E3: autonomy tick — rest → 无状态变化 ----------

async def test_e2e_autonomy_rest(client: AsyncClient):
    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_REST)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200

    # Alice credits 不变
    r = await client.get("/api/agents/1")
    assert r.json()["credits"] == 0


# ---------- E4: autonomy tick — WebSocket 收到 agent_action 事件 ----------

async def test_e2e_autonomy_websocket_event(client: AsyncClient):
    from main import app

    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_CHECKIN)

    with TestClient(app) as sync_client:
        with sync_client.websocket_connect("/api/ws/0") as ws:
            _online = ws.receive_json()  # agent_online for Human

            with p_resolve, p_openai:
                r = await client.post("/api/dev/trigger-autonomy")
                assert r.json()["ok"] is True

            # 收到 agent_action 事件
            event = ws.receive_json()
            assert event["type"] == "system_event"
            assert event["data"]["event"] == "agent_action"
            assert event["data"]["agent_id"] == 1
            assert event["data"]["action"] == "checkin"
            assert event["data"]["agent_name"] == "Alice"
            assert "reason" in event["data"]


# ---------- E5: autonomy tick — 多 agent 混合决策 ----------

async def test_e2e_autonomy_mixed_decisions(client: AsyncClient):
    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_MIXED)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200

    # Alice 打卡 → credits 增加
    r = await client.get("/api/agents/1")
    assert r.json()["credits"] == 10

    # Bob 休息 → credits 不变
    r = await client.get("/api/agents/2")
    assert r.json()["credits"] == 50


# ---------- E6: autonomy tick — LLM 返回无效 JSON → 不崩溃 ----------

async def test_e2e_autonomy_invalid_json(client: AsyncClient):
    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_INVALID_JSON)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    # 所有 agent credits 不变
    r = await client.get("/api/agents/1")
    assert r.json()["credits"] == 0
    r = await client.get("/api/agents/2")
    assert r.json()["credits"] == 50


# ---------- E7: autonomy tick — 余额不足购买 → 静默失败 ----------

async def test_e2e_autonomy_purchase_insufficient(client: AsyncClient):
    # Alice credits=0, 尝试购买 price=8 的商品
    p_resolve, p_openai = _mock_llm(MOCK_DECISIONS_PURCHASE)
    with p_resolve, p_openai:
        r = await client.post("/api/dev/trigger-autonomy")
        assert r.status_code == 200

    # credits 不变
    r = await client.get("/api/agents/1")
    assert r.json()["credits"] == 0

    # 无物品
    r = await client.get("/api/shop/agents/1/items")
    assert r.json() == []

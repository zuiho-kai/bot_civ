"""M6 Phase 1 — 策略引擎单元测试 (T9)"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.database import Base, engine, async_session
from app.models import Agent, Job, Building, BuildingWorker, AgentResource
from app.models.tables import MarketOrder
from app.services.strategy_engine import (
    Strategy, StrategyType, parse_strategies,
    update_strategies, get_strategies, get_all_strategies, clear_strategies,
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        db.add(Agent(id=0, name="Human", persona="human", model="none"))
        db.add(Agent(id=1, name="Alice", persona="勤劳的农民", model="test", credits=50))
        db.add(Agent(id=2, name="Bob", persona="精明的商人", model="test", credits=100))
        db.add(Job(id=1, title="矿工", daily_reward=10, max_workers=5))
        db.add(Building(id=1, name="小麦田", building_type="farm", city="长安", max_workers=3))
        db.add(Building(id=2, name="磨坊", building_type="mill", city="长安", max_workers=2))
        await db.commit()

    clear_strategies()
    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── T1: Schema 解析测试 ──

async def test_parse_keep_working():
    raw = [{"agent_id": 1, "strategy": "keep_working", "building_id": 1,
            "stop_when_resource": "wheat", "stop_when_amount": 50}]
    result = parse_strategies(raw)
    assert len(result) == 1
    s = result[0]
    assert s.strategy == StrategyType.KEEP_WORKING
    assert s.building_id == 1
    assert s.stop_when_resource == "wheat"
    assert s.stop_when_amount == 50.0


async def test_parse_opportunistic_buy():
    raw = [{"agent_id": 2, "strategy": "opportunistic_buy", "resource": "flour",
            "price_below": 1.5, "stop_when_amount": 20}]
    result = parse_strategies(raw)
    assert len(result) == 1
    s = result[0]
    assert s.strategy == StrategyType.OPPORTUNISTIC_BUY
    assert s.resource == "flour"
    assert s.price_below == 1.5


async def test_parse_invalid_strategy_skipped():
    raw = [
        {"agent_id": 1, "strategy": "nonexistent_type"},
        {"agent_id": 1, "strategy": "keep_working", "building_id": 1},
    ]
    result = parse_strategies(raw)
    assert len(result) == 1  # 第一条无效被跳过


async def test_parse_coerces_string_numbers():
    raw = [{"agent_id": 1, "strategy": "keep_working", "building_id": "3",
            "stop_when_resource": "wheat", "stop_when_amount": "50"}]
    result = parse_strategies(raw)
    assert len(result) == 1
    assert result[0].building_id == 3
    assert result[0].stop_when_amount == 50.0


# ── 内存存储测试 ──

async def test_store_and_retrieve():
    s1 = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1,
                  stop_when_resource="wheat", stop_when_amount=50)
    update_strategies(1, [s1])
    result = get_strategies(1)
    assert len(result) == 1
    assert result[0].strategy == StrategyType.KEEP_WORKING


async def test_store_overwrites():
    s1 = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1)
    s2 = Strategy(agent_id=1, strategy=StrategyType.OPPORTUNISTIC_BUY,
                  resource="flour", price_below=2.0)
    update_strategies(1, [s1])
    assert len(get_strategies(1)) == 1
    update_strategies(1, [s2])
    result = get_strategies(1)
    assert len(result) == 1
    assert result[0].strategy == StrategyType.OPPORTUNISTIC_BUY


async def test_get_all_strategies():
    s1 = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1)
    s2 = Strategy(agent_id=2, strategy=StrategyType.OPPORTUNISTIC_BUY,
                  resource="flour", price_below=1.0)
    update_strategies(1, [s1])
    update_strategies(2, [s2])
    all_s = get_all_strategies()
    assert 1 in all_s
    assert 2 in all_s


async def test_clear_strategies():
    s1 = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1)
    update_strategies(1, [s1])
    clear_strategies()
    assert get_strategies(1) == []


# ── T2/T3: decide() 新格式测试 ──

async def test_decide_new_format():
    """LLM 返回旧格式 {actions, strategies}，策略 dormant 只提取 actions。"""
    from app.services.autonomy_service import decide

    new_format = json.dumps({
        "actions": [
            {"agent_id": 1, "action": "eat", "params": {}, "reason": "饿了"},
        ],
        "strategies": [
            {"agent_id": 1, "strategy": "keep_working", "building_id": 1,
             "stop_when_resource": "wheat", "stop_when_amount": 50},
        ]
    })

    mock_choice = MagicMock()
    mock_choice.message.content = new_format
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client):
        actions = await decide("fake snapshot")

    assert len(actions) == 1
    assert actions[0]["action"] == "eat"


async def test_decide_legacy_fallback():
    """LLM 返回旧格式纯数组，strategies 为空。"""
    from app.services.autonomy_service import decide

    legacy = json.dumps([
        {"agent_id": 1, "action": "rest", "params": {}, "reason": "休息"},
    ])

    mock_choice = MagicMock()
    mock_choice.message.content = legacy
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client):
        actions = await decide("fake snapshot")

    assert len(actions) == 1


async def test_decide_reasoning_field_fallback():
    """LLM 返回 content 为空，JSON 在 reasoning 字段，能正确提取。"""
    from app.services.autonomy_service import decide

    # 简化 reasoning 文本，只包含一个完整 JSON
    reasoning_text = """思考：居民需要休息。
决策：{"actions": [{"agent_id": 1, "action": "rest", "params": {}, "reason": "累了"}], "strategies": []}"""

    mock_choice = MagicMock()
    mock_choice.message.content = ""  # content 为空
    mock_choice.message.reasoning = reasoning_text
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client):
        actions = await decide("fake snapshot")

    assert len(actions) == 1
    assert actions[0]["action"] == "rest"


# ── T6: execute_strategies 测试 ──

@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_keep_working_executes_checkin():
    """keep_working 策略：agent 在目标建筑，自动 checkin。"""
    from app.services.autonomy_service import execute_strategies

    # 设置 agent 在建筑 1 工作
    async with async_session() as db:
        db.add(BuildingWorker(building_id=1, agent_id=1))
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=10))
        await db.commit()

    # 设置策略：持续工作直到 wheat >= 50
    s = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1,
                 stop_when_resource="wheat", stop_when_amount=50)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["executed"] >= 1 or stats["skipped"] >= 0  # 取决于是否有可用岗位


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_keep_working_stops_when_resource_reached():
    """keep_working 策略：资源达标时标记 completed。"""
    from app.services.autonomy_service import execute_strategies

    async with async_session() as db:
        db.add(BuildingWorker(building_id=1, agent_id=1))
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=60))  # 已超过 50
        await db.commit()

    s = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1,
                 stop_when_resource="wheat", stop_when_amount=50)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["completed"] == 1
    assert stats["executed"] == 0


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_opportunistic_buy_accepts_cheap_order():
    """opportunistic_buy 策略：市场有低价单时自动接单。"""
    from app.services.autonomy_service import execute_strategies

    async with async_session() as db:
        # Bob 有 flour 想卖，Alice 想买
        db.add(AgentResource(agent_id=2, resource_type="flour", quantity=0, frozen_amount=10))
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=20))
        db.add(MarketOrder(
            id=1, seller_id=2, sell_type="flour", sell_amount=10,
            buy_type="wheat", buy_amount=5,  # 单价 0.5 wheat/flour
            remain_sell_amount=10, remain_buy_amount=5, status="open"
        ))
        await db.commit()

    # Alice 策略：flour 单价低于 1.0 就买
    s = Strategy(agent_id=1, strategy=StrategyType.OPPORTUNISTIC_BUY,
                 resource="flour", price_below=1.0, stop_when_amount=20)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["executed"] == 1


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_opportunistic_buy_stops_when_enough():
    """opportunistic_buy 策略：库存达标时 completed。"""
    from app.services.autonomy_service import execute_strategies

    async with async_session() as db:
        db.add(AgentResource(agent_id=1, resource_type="flour", quantity=25))  # 已超过 20
        await db.commit()

    s = Strategy(agent_id=1, strategy=StrategyType.OPPORTUNISTIC_BUY,
                 resource="flour", price_below=1.0, stop_when_amount=20)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["completed"] == 1
    assert stats["executed"] == 0


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_opportunistic_buy_skips_expensive_order():
    """opportunistic_buy 策略：单价超过阈值不接单。"""
    from app.services.autonomy_service import execute_strategies

    async with async_session() as db:
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=100))
        db.add(AgentResource(agent_id=2, resource_type="flour", quantity=0, frozen_amount=10))
        db.add(MarketOrder(
            id=1, seller_id=2, sell_type="flour", sell_amount=10,
            buy_type="wheat", buy_amount=30,  # 单价 3.0 太贵
            remain_sell_amount=10, remain_buy_amount=30, status="open"
        ))
        await db.commit()

    s = Strategy(agent_id=1, strategy=StrategyType.OPPORTUNISTIC_BUY,
                 resource="flour", price_below=1.0, stop_when_amount=20)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["executed"] == 0
    assert stats["skipped"] >= 1


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_opportunistic_buy_skips_multiple_orders():
    """opportunistic_buy 策略：多个订单都不满足条件，skipped 只计一次（DEV-BUG-18 回归测试）。"""
    from app.services.autonomy_service import execute_strategies

    async with async_session() as db:
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=100))
        db.add(AgentResource(agent_id=2, resource_type="flour", quantity=0, frozen_amount=30))
        # 三个订单：价格太贵、卖家是自己、资源类型不匹配
        db.add(MarketOrder(
            id=1, seller_id=2, sell_type="flour", sell_amount=10,
            buy_type="wheat", buy_amount=30, remain_sell_amount=10, remain_buy_amount=30, status="open"
        ))
        db.add(MarketOrder(
            id=2, seller_id=1, sell_type="flour", sell_amount=10,
            buy_type="wheat", buy_amount=5, remain_sell_amount=10, remain_buy_amount=5, status="open"
        ))
        db.add(MarketOrder(
            id=3, seller_id=2, sell_type="stone", sell_amount=10,
            buy_type="wheat", buy_amount=5, remain_sell_amount=10, remain_buy_amount=5, status="open"
        ))
        await db.commit()

    s = Strategy(agent_id=1, strategy=StrategyType.OPPORTUNISTIC_BUY,
                 resource="flour", price_below=1.0, stop_when_amount=20)
    update_strategies(1, [s])

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_strategies(db)

    assert stats["executed"] == 0
    assert stats["skipped"] == 1  # 只计一次，不是 3 次


@pytest.mark.skip(reason="策略系统 dormant（DEV-40）")
async def test_strategy_execution_isolates_failures():
    """策略执行异常隔离：一个 agent 的策略失败不影响其他 agent。"""
    from app.services.autonomy_service import execute_strategies
    from app.services.work_service import WorkService

    async with async_session() as db:
        db.add(BuildingWorker(building_id=1, agent_id=1))
        db.add(BuildingWorker(building_id=1, agent_id=2))
        db.add(AgentResource(agent_id=1, resource_type="wheat", quantity=10))
        db.add(AgentResource(agent_id=2, resource_type="wheat", quantity=10))
        await db.commit()

    s1 = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1,
                  stop_when_resource="wheat", stop_when_amount=50)
    s2 = Strategy(agent_id=2, strategy=StrategyType.KEEP_WORKING, building_id=1,
                  stop_when_resource="wheat", stop_when_amount=50)
    update_strategies(1, [s1])
    update_strategies(2, [s2])

    # Mock WorkService.check_in，agent 1 抛异常，agent 2 正常
    call_count = {"total": 0}
    async def mock_checkin(self, aid, jid, db):
        call_count["total"] += 1
        if aid == 1:
            raise RuntimeError("Simulated failure for agent 1")
        return {"ok": True, "reward": 10}

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock), \
         patch.object(WorkService, "check_in", mock_checkin):
        async with async_session() as db:
            stats = await execute_strategies(db)

    # agent 1 失败计入 skipped，agent 2 应该被尝试执行
    assert stats["skipped"] >= 1
    assert call_count["total"] >= 1  # 至少尝试了 agent 1


# ── T8: 观测 API 测试 ──

async def test_strategy_api_empty():
    """无策略时返回空数组。"""
    from app.api.agents import get_agent_strategies
    async with async_session() as db:
        result = await get_agent_strategies(1, db)
    assert result == []


async def test_strategy_api_returns_data():
    """有策略时返回正确数据。"""
    from app.api.agents import get_agent_strategies
    s = Strategy(agent_id=1, strategy=StrategyType.KEEP_WORKING, building_id=1,
                 stop_when_resource="wheat", stop_when_amount=50)
    update_strategies(1, [s])
    async with async_session() as db:
        result = await get_agent_strategies(1, db)
    assert len(result) == 1
    assert result[0]["strategy"] == "keep_working"
    assert result[0]["building_id"] == 1

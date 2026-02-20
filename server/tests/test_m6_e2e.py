"""M6 Phase 1 E2E tests: 策略自动机端到端验证

验证两个策略类型：
1. keep_working — 持续在建筑工作直到资源达标
2. opportunistic_buy — 市场出现低价资源时自动接单
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.core.database import Base, engine, async_session
from app.models import Agent, Building, AgentResource, MarketOrder
from app.services.strategy_engine import Strategy, StrategyType, update_strategies, clear_strategies

pytestmark = [pytest.mark.asyncio, pytest.mark.skip(reason="策略系统 dormant（DEV-40）")]


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables + seed, tear down after each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
        db.add(Agent(id=1, name="张三", persona="农民", model="none", status="idle",
                     satiety=80, mood=80, stamina=100, credits=50))
        db.add(Agent(id=2, name="李四", persona="商人", model="none", status="idle",
                     satiety=80, mood=80, stamina=100, credits=100))
        db.add(Building(id=3, name="农田A", building_type="farm", city="长安", max_workers=2))
        # accept_order 从 AgentResource 表检查 credits，需要在此表中初始化
        db.add(AgentResource(agent_id=2, resource_type="credits", quantity=100.0, frozen_amount=0.0))
        await db.commit()

    # 清空策略存储
    clear_strategies()

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    clear_strategies()


@pytest_asyncio.fixture
async def client():
    from main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ---------- E1: keep_working 策略端到端 ----------

async def test_e1_keep_working_strategy(client: AsyncClient):
    """
    场景：张三设置策略"持续在农田工作直到小麦达到 50"
    验证：自动机自动执行 checkin，资源达标后停止
    """
    # 1. 张三应聘农田
    r = await client.post("/api/cities/长安/buildings/3/workers", json={"agent_id": 1})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 2. 设置策略：持续工作直到 wheat >= 50
    strategy = Strategy(
        agent_id=1,
        strategy=StrategyType.KEEP_WORKING,
        building_id=3,
        stop_when_resource="wheat",
        stop_when_amount=50
    )
    update_strategies(1, [strategy])

    # 3. 触发生产（production_tick 会为所有在建筑工作的 Agent 生产资源）
    r = await client.post("/api/cities/长安/production-tick")
    assert r.status_code == 200

    # 4. 验证资源增加（farm 每次生产 wheat=10）
    r = await client.get("/api/agents/1/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("wheat", 0) == 10

    # 5. 检查策略状态（wheat=10 < 50，策略仍然活跃）
    from app.services.autonomy_service import execute_strategies
    async with async_session() as db:
        stats = await execute_strategies(db)
        await db.commit()

    # keep_working 策略不执行动作，只是检查终止条件
    assert stats["completed"] == 0  # 还没达标
    assert stats["skipped"] >= 1  # 策略被跳过（因为不需要执行动作）

    # 6. 手动增加资源到接近目标（模拟多轮生产）
    async with async_session() as db:
        # 更新现有资源记录
        result = await db.execute(
            select(AgentResource).where(
                AgentResource.agent_id == 1,
                AgentResource.resource_type == "wheat"
            )
        )
        wheat_res = result.scalar_one()
        wheat_res.quantity = 45
        await db.commit()

    # 7. 再次触发生产（45 + 10 = 55）
    r = await client.post("/api/cities/长安/production-tick")
    assert r.status_code == 200

    # 8. 验证资源达标（55 >= 50）
    r = await client.get("/api/agents/1/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("wheat", 0) >= 50

    # 9. 检查策略状态（wheat >= 50，策略应该标记为完成）
    async with async_session() as db:
        stats = await execute_strategies(db)
        await db.commit()

    assert stats["completed"] >= 1  # 策略已完成


# ---------- E2: opportunistic_buy 策略端到端 ----------

async def test_e2_opportunistic_buy_strategy(client: AsyncClient):
    """
    场景：李四设置策略"小麦粉低于 1.5 就买，直到库存达到 20"
    验证：自动机扫描市场挂单，符合条件自动接单
    """
    # 1. 市场上挂一个低价单（flour 价格 1.2 < 1.5）
    async with async_session() as db:
        db.add(MarketOrder(
            id=101,
            seller_id=0,
            sell_type="flour",
            sell_amount=30,
            buy_type="credits",
            buy_amount=36,  # 30 flour for 36 credits, 单价 1.2
            status="open",
            remain_sell_amount=30,
            remain_buy_amount=36
        ))
        await db.commit()

    # 2. 设置策略：flour 低于 1.5 就买，直到库存 >= 20
    strategy = Strategy(
        agent_id=2,
        strategy=StrategyType.OPPORTUNISTIC_BUY,
        resource="flour",
        price_below=1.5,
        stop_when_amount=20
    )
    update_strategies(2, [strategy])

    # 3. 执行策略（flour=0 < 20，市场有低价单，应该接单）
    from app.services.autonomy_service import execute_strategies
    async with async_session() as db:
        stats = await execute_strategies(db)
        await db.commit()

    assert stats["executed"] >= 1  # 至少执行了 1 次接单

    # 4. 验证资源增加
    r = await client.get("/api/agents/2/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("flour", 0) >= 20  # 应该买了至少 20

    # 5. 再次执行策略（flour >= 20，应该跳过）
    async with async_session() as db:
        stats = await execute_strategies(db)
        await db.commit()

    assert stats["completed"] >= 1  # 策略已完成
    assert stats["executed"] == 0  # 不再执行


# ---------- E3: opportunistic_buy 跳过高价单 ----------

async def test_e3_opportunistic_buy_skips_expensive(client: AsyncClient):
    """
    场景：市场只有高价单（flour 价格 2.0 > 1.5）
    验证：自动机跳过，不执行接单
    """
    # 1. 市场上挂一个高价单（flour 价格 2.0 > 1.5）
    async with async_session() as db:
        db.add(MarketOrder(
            id=102,
            seller_id=0,
            sell_type="flour",
            sell_amount=30,
            buy_type="credits",
            buy_amount=60,  # 30 flour for 60 credits, 单价 2.0
            status="open",
            remain_sell_amount=30,
            remain_buy_amount=60
        ))
        await db.commit()

    # 2. 设置策略：flour 低于 1.5 就买
    strategy = Strategy(
        agent_id=2,
        strategy=StrategyType.OPPORTUNISTIC_BUY,
        resource="flour",
        price_below=1.5,
        stop_when_amount=20
    )
    update_strategies(2, [strategy])

    # 3. 执行策略（市场无低价单，应该跳过）
    from app.services.autonomy_service import execute_strategies
    async with async_session() as db:
        stats = await execute_strategies(db)
        await db.commit()

    assert stats["skipped"] >= 1  # 跳过了
    assert stats["executed"] == 0  # 没有执行

    # 4. 验证资源未变化
    r = await client.get("/api/agents/2/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("flour", 0) == 0  # 没买到


# ---------- E4: 策略观测 API ----------

async def test_e4_strategy_observation_api(client: AsyncClient):
    """
    场景：设置策略后，通过 API 查看当前活跃策略
    验证：GET /api/agents/{id}/strategies 返回正确数据
    """
    # 1. 设置两条策略
    strategies = [
        Strategy(
            agent_id=1,
            strategy=StrategyType.KEEP_WORKING,
            building_id=3,
            stop_when_resource="wheat",
            stop_when_amount=50
        ),
        Strategy(
            agent_id=1,
            strategy=StrategyType.OPPORTUNISTIC_BUY,
            resource="flour",
            price_below=1.5,
            stop_when_amount=20
        )
    ]
    update_strategies(1, strategies)

    # 2. 查询策略
    r = await client.get("/api/agents/1/strategies")
    assert r.status_code == 200
    data = r.json()

    assert len(data) == 2
    assert data[0]["strategy"] == "keep_working"
    assert data[0]["building_id"] == 3
    assert data[0]["stop_when_resource"] == "wheat"
    assert data[0]["stop_when_amount"] == 50

    assert data[1]["strategy"] == "opportunistic_buy"
    assert data[1]["resource"] == "flour"
    assert data[1]["price_below"] == 1.5
    assert data[1]["stop_when_amount"] == 20

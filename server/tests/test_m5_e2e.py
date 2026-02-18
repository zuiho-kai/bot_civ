"""M5 E2E tests: 官府田闭环 + 吃饭恢复 + 每日结算 + 体力不足 + 满员竞争 + 完整生命周期 + 记忆CRUD + attributes路由"""

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.core.database import Base, engine, async_session
from app.models import Agent, Building, BuildingWorker, AgentResource

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables + seed, tear down after each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
        db.add(Agent(id=1, name="张三", persona="农民", model="none", status="idle",
                     satiety=50, mood=60, stamina=50, credits=0))
        db.add(Agent(id=2, name="李四", persona="工人", model="none", status="idle",
                     satiety=80, mood=80, stamina=80, credits=0))
        db.add(Agent(id=3, name="王五", persona="商人", model="none", status="idle",
                     satiety=80, mood=80, stamina=80, credits=0))
        db.add(Building(id=1, name="官府田", building_type="gov_farm", city="长安", max_workers=2))
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


# ---------- E1: 官府田完整生产闭环 ----------

async def test_e1_gov_farm_production_loop(client: AsyncClient):
    # 分配工人
    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 1})
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 触发生产
    r = await client.post("/api/cities/长安/production-tick")
    assert r.status_code == 200

    # 查询资源: flour=5
    r = await client.get("/api/agents/1/resources")
    assert r.status_code == 200
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("flour", 0) == 5

    # 查询属性: stamina=35 (50-15)
    r = await client.get("/api/agents/1/attributes")
    assert r.status_code == 200
    assert r.json()["stamina"] == 35


# ---------- E2: 吃饭恢复属性 ----------

async def test_e2_eat_restore_attributes(client: AsyncClient):
    # 先给 agent 面粉
    async with async_session() as db:
        db.add(AgentResource(agent_id=1, resource_type="flour", quantity=2))
        await db.commit()

    # 吃饭
    r = await client.post("/api/agents/1/eat")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["satiety"] == 80   # 50+30
    assert body["mood"] == 70      # 60+10
    assert body["stamina"] == 70   # 50+20

    # 确认资源减少
    r = await client.get("/api/agents/1/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources["flour"] == 1


# ---------- E3: 每日属性结算 ----------

async def test_e3_daily_decay(client: AsyncClient):
    # 初始: satiety=50, mood=60, stamina=50
    r = await client.post("/api/cities/长安/daily-decay")
    assert r.status_code == 200

    r = await client.get("/api/agents/1/attributes")
    body = r.json()
    assert body["satiety"] == 35   # 50-15
    assert body["stamina"] == 65   # 50+15
    # satiety after decay = 35, which is >= 30, so mood unchanged
    assert body["mood"] == 60


# ---------- E4: 体力不足无法生产 ----------

async def test_e4_low_stamina_no_production(client: AsyncClient):
    # 设置 agent stamina=10
    async with async_session() as db:
        agent = await db.get(Agent, 1)
        agent.stamina = 10
        await db.commit()

    # 分配工人
    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 1})
    assert r.json()["ok"] is True

    # 触发生产
    r = await client.post("/api/cities/长安/production-tick")
    assert r.status_code == 200

    # flour 仍为 0
    r = await client.get("/api/agents/1/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources.get("flour", 0) == 0

    # stamina 不变
    r = await client.get("/api/agents/1/attributes")
    assert r.json()["stamina"] == 10


# ---------- E5: 应聘满员竞争 ----------

async def test_e5_assign_full_competition(client: AsyncClient):
    # max_workers=2, 3 人竞争
    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 1})
    assert r.json()["ok"] is True

    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 2})
    assert r.json()["ok"] is True

    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 3})
    assert r.json()["ok"] is False
    assert "满" in r.json()["reason"]


# ---------- E6: 应聘→生产→吃饭→离职 完整生命周期 ----------

async def test_e6_full_lifecycle(client: AsyncClient):
    # 1. 应聘
    r = await client.post("/api/cities/长安/buildings/1/workers", json={"agent_id": 1})
    assert r.json()["ok"] is True

    # 2. 生产 (flour+5, stamina 50→35)
    r = await client.post("/api/cities/长安/production-tick")
    assert r.status_code == 200

    # 3. 吃饭 (flour-1=4, satiety 50→80, mood 60→70, stamina 35→55)
    r = await client.post("/api/agents/1/eat")
    body = r.json()
    assert body["ok"] is True
    assert body["satiety"] == 80
    assert body["mood"] == 70
    assert body["stamina"] == 55  # 35+20

    # 4. 离职
    r = await client.delete("/api/cities/长安/buildings/1/workers/1")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 5. 验证最终状态
    r = await client.get("/api/agents/1/attributes")
    attrs = r.json()
    assert attrs["satiety"] == 80
    assert attrs["mood"] == 70
    assert attrs["stamina"] == 55

    r = await client.get("/api/agents/1/resources")
    resources = {item["resource_type"]: item["quantity"] for item in r.json()}
    assert resources["flour"] == 4


# ---------- E7: 记忆 CRUD 完整流程 ----------

async def test_e7_memory_crud(client: AsyncClient):
    # 1. 创建
    r = await client.post("/api/memories", json={
        "agent_id": 1, "content": "今天在官府田工作", "memory_type": "short",
    })
    assert r.status_code == 200
    memory_id = r.json()["id"]

    # 2. 列表确认
    r = await client.get("/api/memories", params={"agent_id": 1})
    assert r.status_code == 200
    items = r.json()["items"]
    assert any(m["id"] == memory_id for m in items)

    # 3. 更新
    r = await client.put(f"/api/memories/{memory_id}", json={
        "content": "今天在官府田工作，收获了5份面粉",
    })
    assert r.status_code == 200

    # 4. 确认更新
    r = await client.get(f"/api/memories/{memory_id}")
    assert r.status_code == 200
    assert r.json()["content"] == "今天在官府田工作，收获了5份面粉"

    # 5. 删除
    r = await client.delete(f"/api/memories/{memory_id}")
    assert r.status_code == 200

    # 6. 确认删除
    r = await client.get(f"/api/memories/{memory_id}")
    assert r.status_code == 404


# ---------- E8: attributes 路由 ----------

async def test_e8_attributes_endpoint(client: AsyncClient):
    r = await client.get("/api/agents/1/attributes")
    assert r.status_code == 200
    body = r.json()
    assert body["satiety"] == 50
    assert body["mood"] == 60
    assert body["stamina"] == 50

    # 不存在的 agent
    r = await client.get("/api/agents/999/attributes")
    assert r.status_code == 404

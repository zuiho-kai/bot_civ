"""M5 单元测试: daily_attribute_decay + production_tick gov_farm + eat_food 三维 + assign_worker 跨建筑 + memory CRUD"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.models import Agent, Building, BuildingWorker, AgentResource, Memory, ProductionLog
from app.services.city_service import (
    daily_attribute_decay, production_tick, eat_food, assign_worker,
)
from app.services.memory_admin_service import (
    create_memory, get_memory_detail, update_memory, delete_memory, list_memories,
)

pytestmark = pytest.mark.asyncio


async def _seed_agent(db, *, id=1, satiety=80, mood=60, stamina=50):
    agent = Agent(id=id, name=f"TestAgent{id}", persona="test", model="none", status="idle",
                  satiety=satiety, mood=mood, stamina=stamina)
    db.add(agent)
    await db.flush()
    return agent


async def _seed_building(db, *, id=1, building_type="gov_farm", max_workers=3, city="长安"):
    b = Building(id=id, name=f"Test{building_type}", building_type=building_type,
                 city=city, max_workers=max_workers)
    db.add(b)
    await db.flush()
    return b


async def _seed_worker(db, building_id, agent_id):
    bw = BuildingWorker(building_id=building_id, agent_id=agent_id)
    db.add(bw)
    await db.flush()
    return bw


async def _seed_agent_resource(db, agent_id, resource_type, quantity):
    ar = AgentResource(agent_id=agent_id, resource_type=resource_type, quantity=quantity)
    db.add(ar)
    await db.flush()
    return ar


# ========== U1: daily_attribute_decay 正常衰减 ==========

async def test_u1_decay_normal(db):
    await _seed_agent(db, satiety=80, mood=60, stamina=50)
    # need human agent for HUMAN_ID=0 exclusion
    db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
    await db.flush()

    await daily_attribute_decay(db)

    agent = await db.get(Agent, 1)
    assert agent.satiety == 65  # 80-15
    assert agent.stamina == 65  # 50+15
    assert agent.mood == 60     # satiety>=30, no mood decay


# ========== U2: daily_attribute_decay 饱腹度低 ==========

async def test_u2_decay_low_satiety(db):
    db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
    await _seed_agent(db, satiety=20, mood=60, stamina=50)
    await db.flush()

    await daily_attribute_decay(db)

    agent = await db.get(Agent, 1)
    assert agent.satiety == 5   # 20-15
    assert agent.stamina == 65  # 50+15
    assert agent.mood == 50     # satiety=5 < 30 → mood-10


# ========== U3: daily_attribute_decay 饱腹度为零 ==========

async def test_u3_decay_zero_satiety(db):
    db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
    await _seed_agent(db, satiety=0, mood=60, stamina=50)
    await db.flush()

    await daily_attribute_decay(db)

    agent = await db.get(Agent, 1)
    assert agent.satiety == 0   # 0-15 clamped to 0
    assert agent.stamina == 65  # 50+15
    assert agent.mood == 40     # satiety=0 → mood-20


# ========== U4: daily_attribute_decay 属性钳制 ==========

async def test_u4_decay_clamp(db):
    db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
    await _seed_agent(db, satiety=10, mood=30, stamina=95)
    await db.flush()

    await daily_attribute_decay(db)

    agent = await db.get(Agent, 1)
    assert agent.satiety == 0    # 10-15 clamped to 0
    assert agent.stamina == 100  # 95+15 clamped to 100
    assert agent.mood == 10      # satiety=0 → mood 30-20=10


# ========== U5: production_tick gov_farm 正常生产 ==========

async def test_u5_gov_farm_production(db):
    await _seed_agent(db, stamina=50)
    b = await _seed_building(db, building_type="gov_farm")
    await _seed_worker(db, b.id, 1)
    await db.flush()

    await production_tick("长安", db)

    # flour +5
    result = await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "flour")
    )
    ar = result.scalar()
    assert ar is not None
    assert ar.quantity == 5

    # stamina 50-15=35
    agent = await db.get(Agent, 1)
    assert agent.stamina == 35

    # production log exists
    log_result = await db.execute(select(ProductionLog))
    logs = log_result.scalars().all()
    assert len(logs) == 1
    assert logs[0].output_type == "flour"
    assert logs[0].output_qty == 5


# ========== U6: production_tick gov_farm 体力不足跳过 ==========

async def test_u6_gov_farm_low_stamina(db):
    await _seed_agent(db, stamina=15)
    b = await _seed_building(db, building_type="gov_farm")
    await _seed_worker(db, b.id, 1)
    await db.flush()

    await production_tick("长安", db)

    # flour still 0
    result = await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "flour")
    )
    ar = result.scalar()
    assert ar is None or ar.quantity == 0

    # stamina unchanged
    agent = await db.get(Agent, 1)
    assert agent.stamina == 15

    # no production log
    log_result = await db.execute(select(ProductionLog))
    assert len(log_result.scalars().all()) == 0


# ========== U7: production_tick farm 不受影响 ==========

async def test_u7_farm_still_works(db):
    await _seed_agent(db, stamina=50)
    b = await _seed_building(db, building_type="farm")
    await _seed_worker(db, b.id, 1)
    await db.flush()

    await production_tick("长安", db)

    # wheat +10
    result = await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )
    ar = result.scalar()
    assert ar is not None
    assert ar.quantity == 10

    agent = await db.get(Agent, 1)
    assert agent.stamina == 35  # 50-15


# ========== U8: production_tick 不再做属性衰减 ==========

async def test_u8_production_no_decay(db):
    await _seed_agent(db, satiety=80, mood=60, stamina=50)
    await db.flush()

    await production_tick("长安", db)

    agent = await db.get(Agent, 1)
    assert agent.satiety == 80  # unchanged
    assert agent.mood == 60     # unchanged


# ========== U9: eat_food 恢复三维属性 ==========

async def test_u9_eat_food_restore(db):
    await _seed_agent(db, satiety=50, mood=60, stamina=40)
    await _seed_agent_resource(db, 1, "flour", 3)
    await db.flush()

    result = await eat_food(1, db)
    assert result["ok"] is True
    assert result["satiety"] == 80   # 50+30
    assert result["mood"] == 70      # 60+10
    assert result["stamina"] == 60   # 40+20

    # flour 3→2
    ar = await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "flour")
    )
    assert ar.scalar().quantity == 2


# ========== U10: eat_food 无面粉失败 ==========

async def test_u10_eat_no_flour(db):
    await _seed_agent(db, satiety=50, mood=60, stamina=40)
    await db.flush()

    result = await eat_food(1, db)
    assert result["ok"] is False

    agent = await db.get(Agent, 1)
    assert agent.satiety == 50
    assert agent.mood == 60
    assert agent.stamina == 40


# ========== U11: eat_food 属性上限钳制 ==========

async def test_u11_eat_clamp(db):
    await _seed_agent(db, satiety=90, mood=95, stamina=90)
    await _seed_agent_resource(db, 1, "flour", 1)
    await db.flush()

    result = await eat_food(1, db)
    assert result["ok"] is True
    assert result["satiety"] == 100  # 90+30 clamped
    assert result["mood"] == 100     # 95+10 clamped
    assert result["stamina"] == 100  # 90+20 clamped


# ========== U12: assign_worker 跨建筑检查 ==========

async def test_u12_assign_cross_building_reject(db):
    await _seed_agent(db)
    b1 = await _seed_building(db, id=1, building_type="gov_farm")
    b2 = await _seed_building(db, id=2, building_type="farm")
    await _seed_worker(db, b1.id, 1)
    await db.flush()

    result = await assign_worker("长安", b2.id, 1, db)
    assert result["ok"] is False
    assert "已在其他建筑" in result["reason"]


# ========== U13: assign_worker 正常应聘 ==========

async def test_u13_assign_normal(db):
    await _seed_agent(db)
    b = await _seed_building(db, building_type="gov_farm", max_workers=3)
    await db.flush()

    result = await assign_worker("长安", b.id, 1, db)
    assert result["ok"] is True

    bw_result = await db.execute(
        select(BuildingWorker).where(BuildingWorker.building_id == b.id, BuildingWorker.agent_id == 1)
    )
    assert bw_result.scalar() is not None


# ========== U14: assign_worker 满员拒绝 ==========

async def test_u14_assign_full(db):
    await _seed_agent(db, id=1)
    await _seed_agent(db, id=2)
    await _seed_agent(db, id=3)
    b = await _seed_building(db, max_workers=2)
    await _seed_worker(db, b.id, 1)
    await _seed_worker(db, b.id, 2)
    await db.flush()

    result = await assign_worker("长安", b.id, 3, db)
    assert result["ok"] is False
    assert "满" in result["reason"]


# ========== U15: memory CRUD ==========

async def test_u15_memory_crud(db):
    await _seed_agent(db)
    await db.flush()

    # create
    mem = await create_memory(1, "short", "今天在官府田工作很累", db)
    assert mem["id"] is not None
    mid = mem["id"]

    # read
    detail = await get_memory_detail(mid, db)
    assert detail["content"] == "今天在官府田工作很累"

    # update
    updated = await update_memory(mid, "今天在官府田工作很累但很充实", None, db)
    assert updated["content"] == "今天在官府田工作很累但很充实"

    # confirm update
    detail2 = await get_memory_detail(mid, db)
    assert detail2["content"] == "今天在官府田工作很累但很充实"

    # delete
    ok = await delete_memory(mid, db)
    assert ok is True

    # confirm deleted
    detail3 = await get_memory_detail(mid, db)
    assert detail3 is None


# ========== U16: memory list with keyword filter ==========

async def test_u16_memory_keyword(db):
    await _seed_agent(db)
    await db.flush()

    await create_memory(1, "short", "在官府田种地", db)
    await create_memory(1, "short", "去磨坊磨面粉", db)
    await create_memory(1, "short", "在官府田吃饭", db)

    result = await list_memories(1, None, "官府田", 1, 20, db)
    assert result["total"] == 2
    contents = [m["content"] for m in result["items"]]
    assert "去磨坊磨面粉" not in contents

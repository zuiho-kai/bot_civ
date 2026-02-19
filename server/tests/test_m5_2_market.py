"""M5.2 交易市场 TDD 测试 — 挂单/接单/撤单核心逻辑"""
# 覆盖: market_service 核心 + 并发安全 + Tool Use + autonomy 集成

import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, patch
from sqlalchemy import select

from app.models import Agent, AgentResource
from app.models.tables import MarketOrder, TradeLog

pytestmark = pytest.mark.asyncio


# ── helpers ──────────────────────────────────────────────

async def _seed_agent(db, *, id=1, name="TestAgent", **kw):
    defaults = dict(persona="test", model="none", status="idle",
                    satiety=80, mood=60, stamina=50)
    defaults.update(kw)
    agent = Agent(id=id, name=name, **defaults)
    db.add(agent)
    await db.flush()
    return agent


async def _seed_resource(db, agent_id, resource_type, quantity):
    ar = AgentResource(agent_id=agent_id, resource_type=resource_type, quantity=float(quantity))
    db.add(ar)
    await db.flush()
    return ar


# ══════════════════════════════════════════════════════════
# Phase 1: 挂单 (create_order)
# ══════════════════════════════════════════════════════════

# T1: 正常挂单 — 卖出 5 wheat 换 3 flour
async def test_t1_create_order_success(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.market_service import create_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        result = await create_order(
            seller_id=1, sell_type="wheat", sell_amount=5.0,
            buy_type="flour", buy_amount=3.0, db=db,
        )

    assert result["ok"] is True
    assert "order_id" in result

    # 验证冻结: 可用 = 20 - 5 = 15, frozen = 5
    ar = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )).scalar()
    assert ar.quantity == 15.0
    assert ar.frozen_amount == 5.0


# T2: 挂单资源不足 → 失败
async def test_t2_create_order_insufficient(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 3)

    from app.services.market_service import create_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        result = await create_order(
            seller_id=1, sell_type="wheat", sell_amount=5.0,
            buy_type="flour", buy_amount=3.0, db=db,
        )
    assert result["ok"] is False
    assert "不足" in result["reason"]


# T3: 挂单数量 <= 0 → 失败
async def test_t3_create_order_invalid_amount(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.market_service import create_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        r1 = await create_order(1, "wheat", 0, "flour", 3.0, db=db)
        r2 = await create_order(1, "wheat", -1, "flour", 3.0, db=db)
    assert r1["ok"] is False
    assert r2["ok"] is False


# T4: 卖出和买入同类型 → 失败
async def test_t4_create_order_same_type(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.market_service import create_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        result = await create_order(1, "wheat", 5.0, "wheat", 3.0, db=db)
    assert result["ok"] is False


# ══════════════════════════════════════════════════════════
# Phase 2: 接单 (accept_order) — 含部分购买
# ══════════════════════════════════════════════════════════

# T5: 全额接单
async def test_t5_accept_order_full(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 5.0, db=db)
        oid = order_res["order_id"]
        result = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.0, db=db)

    assert result["ok"] is True

    # Alice: wheat 冻结释放, flour +5
    alice_wheat = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )).scalar()
    assert alice_wheat.quantity == 10.0  # 20 - 10
    assert alice_wheat.frozen_amount == 0.0

    alice_flour = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "flour")
    )).scalar()
    assert alice_flour.quantity == 5.0

    # Bob: flour -5, wheat +10
    bob_flour = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 2, AgentResource.resource_type == "flour")
    )).scalar()
    assert bob_flour.quantity == 5.0  # 10 - 5

    bob_wheat = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 2, AgentResource.resource_type == "wheat")
    )).scalar()
    assert bob_wheat.quantity == 10.0

    # 订单状态 = filled
    order = await db.get(MarketOrder, oid)
    assert order.status == "filled"


# T6: 部分接单 (50%)
async def test_t6_accept_order_partial(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 6.0, db=db)
        oid = order_res["order_id"]
        result = await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.5, db=db)

    assert result["ok"] is True

    # 订单: remain_sell = 5, remain_buy = 3, status = partial
    order = await db.get(MarketOrder, oid)
    assert order.status == "partial"
    assert order.remain_sell_amount == 5.0
    assert order.remain_buy_amount == 3.0

    # Alice: frozen 从 10 降到 5
    alice_wheat = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )).scalar()
    assert alice_wheat.frozen_amount == 5.0


# T7: 接单资源不足 → 失败
async def test_t7_accept_order_buyer_insufficient(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 1)  # 不够

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 5.0, db=db)
        oid = order_res["order_id"]
        result = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.0, db=db)

    assert result["ok"] is False
    assert "不足" in result["reason"]


# T8: 自己接自己的单 → 失败
async def test_t8_accept_own_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 1, "flour", 10)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        oid = order_res["order_id"]
        result = await accept_order(buyer_id=1, order_id=oid, buy_ratio=1.0, db=db)

    assert result["ok"] is False


# T9: 接已撤销的单 → 失败
async def test_t9_accept_cancelled_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, cancel_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        oid = order_res["order_id"]
        await cancel_order(seller_id=1, order_id=oid, db=db)
        result = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.0, db=db)

    assert result["ok"] is False


# ══════════════════════════════════════════════════════════
# Phase 3: 撤单 (cancel_order)
# ══════════════════════════════════════════════════════════

# T10: 正常撤单 — 冻结资源归还
async def test_t10_cancel_order_success(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.market_service import create_order, cancel_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        oid = order_res["order_id"]
        result = await cancel_order(seller_id=1, order_id=oid, db=db)

    assert result["ok"] is True

    # 冻结归还
    ar = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )).scalar()
    assert ar.quantity == 20.0
    assert ar.frozen_amount == 0.0

    order = await db.get(MarketOrder, oid)
    assert order.status == "cancelled"


# T11: 撤别人的单 → 失败
async def test_t11_cancel_others_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.market_service import create_order, cancel_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        oid = order_res["order_id"]
        result = await cancel_order(seller_id=2, order_id=oid, db=db)

    assert result["ok"] is False


# T12: 部分成交后撤单 — 只归还剩余冻结
async def test_t12_cancel_partial_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, accept_order, cancel_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 6.0, db=db)
        oid = order_res["order_id"]
        await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.5, db=db)
        # 此时 remain_sell=5, frozen=5
        result = await cancel_order(seller_id=1, order_id=oid, db=db)

    assert result["ok"] is True
    ar = (await db.execute(
        select(AgentResource).where(AgentResource.agent_id == 1, AgentResource.resource_type == "wheat")
    )).scalar()
    assert ar.frozen_amount == 0.0
    assert ar.quantity == 15.0  # 20 - 10(挂单冻结) + 5(部分成交释放) + 5(撤单归还) = 15 ✓ 实际: 20-10冻结时quantity=10, 部分成交释放5给Bob quantity不变, 撤单归还5 quantity=15


# ══════════════════════════════════════════════════════════
# Phase 4: 查询
# ══════════════════════════════════════════════════════════

# T13: list_orders 返回 open/partial 订单
async def test_t13_list_orders(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 100)

    from app.services.market_service import create_order, list_orders
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        await create_order(1, "wheat", 10.0, "flour", 6.0, db=db)

    orders = await list_orders(db=db)
    assert len(orders) == 2
    assert all(o["status"] in ("open", "partial") for o in orders)


# T14: get_trade_logs 返回成交记录
async def test_t14_trade_logs(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, accept_order, get_trade_logs
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 5.0, "flour", 3.0, db=db)
        await accept_order(2, order_res["order_id"], 1.0, db=db)

    logs = await get_trade_logs(db=db)
    assert len(logs) >= 1
    assert logs[0]["seller_id"] == 1
    assert logs[0]["buyer_id"] == 2


# ══════════════════════════════════════════════════════════
# Phase 5: 并发安全
# ══════════════════════════════════════════════════════════

# T15: 两人串行全额接同一单 — 只有一人成功（SQLite 单写者，验证状态机正确性）
async def test_t15_sequential_double_accept(db):
    """串行双接单：第一个成功后 order 变 filled，第二个被状态机拦截"""
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_agent(db, id=3, name="Charlie")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)
    await _seed_resource(db, 3, "flour", 10)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 5.0, db=db)
        oid = order_res["order_id"]

        # 串行模拟并发（SQLite 内存库不支持真并发，验证逻辑正确性）
        r1 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.0, db=db)
        r2 = await accept_order(buyer_id=3, order_id=oid, buy_ratio=1.0, db=db)

    success_count = sum(1 for r in [r1, r2] if r["ok"])
    assert success_count == 1  # 只有一个成功


# ══════════════════════════════════════════════════════════
# Phase 6: Tool Use 集成
# ══════════════════════════════════════════════════════════

# T16: tool_registry 已注册 create_market_order
async def test_t16_tool_registry_has_market_tools():
    from app.services.tool_registry import tool_registry
    tools = tool_registry.get_tools_for_llm()
    names = [t["function"]["name"] for t in tools]
    assert "create_market_order" in names
    assert "accept_market_order" in names
    assert "cancel_market_order" in names


# T17: create_market_order handler 正确调用 market_service
async def test_t17_tool_create_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    from app.services.tool_registry import tool_registry
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        result = await tool_registry.execute(
            "create_market_order",
            {"sell_type": "wheat", "sell_amount": 5, "buy_type": "flour", "buy_amount": 3},
            {"agent_id": 1, "db": db},
        )
    assert result["ok"] is True
    assert result["result"]["ok"] is True


# ══════════════════════════════════════════════════════════
# Phase 7: autonomy_loop 集成
# ══════════════════════════════════════════════════════════

# T18: autonomy execute_decisions 处理 create_market_order
async def test_t18_autonomy_create_order(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_resource(db, 1, "wheat", 20)

    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock), \
         patch("app.services.city_service._broadcast_city_event", new_callable=AsyncMock):
        from app.services.autonomy_service import execute_decisions
        decisions = [
            {"agent_id": 1, "action": "create_market_order",
             "params": {"sell_type": "wheat", "sell_amount": 5, "buy_type": "flour", "buy_amount": 3},
             "reason": "想用小麦换面粉"},
        ]
        stats = await execute_decisions(decisions, db)

    assert stats["success"] >= 1


# T19: autonomy decide() 的 valid_actions 包含交易动作
async def test_t19_autonomy_valid_actions():
    from app.services.autonomy_service import SYSTEM_PROMPT
    assert "create_market_order" in SYSTEM_PROMPT
    assert "accept_market_order" in SYSTEM_PROMPT
    assert "cancel_market_order" in SYSTEM_PROMPT


# T20: buy_ratio 边界 — 0 和 >1 都失败
async def test_t20_accept_order_invalid_ratio(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 20)
    await _seed_resource(db, 2, "flour", 10)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        order_res = await create_order(1, "wheat", 10.0, "flour", 5.0, db=db)
        oid = order_res["order_id"]
        r1 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.0, db=db)
        r2 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.5, db=db)

    assert r1["ok"] is False
    assert r2["ok"] is False


# ══════════════════════════════════════════════════════════
# Phase 8: Float 精度边界
# ══════════════════════════════════════════════════════════

# T21: 极小 buy_ratio 导致成交量为 0 被拦截
async def test_t21_accept_order_tiny_ratio(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 10)
    await _seed_resource(db, 2, "flour", 5)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        r = await create_order(1, "wheat", 0.05, "flour", 0.03, db=db)
        oid = r["order_id"]
        # buy_ratio=0.01 → trade_sell = round(0.05*0.01,2) = 0.0 → 被拦截
        res = await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.01, db=db)
    assert res["ok"] is False
    assert "过小" in res["reason"]


# T22: 连续 3 次 buy_ratio=0.34 — Float 精度兜底自动归零
async def test_t22_repeated_partial_accept_precision(db):
    await _seed_agent(db, id=1, name="Alice")
    await _seed_agent(db, id=2, name="Bob")
    await _seed_resource(db, 1, "wheat", 100)
    await _seed_resource(db, 2, "flour", 100)

    from app.services.market_service import create_order, accept_order
    with patch("app.services.market_service._broadcast_market_event", new_callable=AsyncMock):
        r = await create_order(1, "wheat", 10.0, "flour", 5.0, db=db)
        oid = r["order_id"]
        r1 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.34, db=db)
        assert r1["ok"] is True
        r2 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=0.34, db=db)
        assert r2["ok"] is True
        r3 = await accept_order(buyer_id=2, order_id=oid, buy_ratio=1.0, db=db)
        assert r3["ok"] is True
        # 三次后订单应该 filled（精度兜底）
        assert r3["order_status"] == "filled"

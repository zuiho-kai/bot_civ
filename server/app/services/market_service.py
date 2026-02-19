"""M5.2 交易市场核心服务 — 挂单/接单/撤单"""
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import AgentResource
from ..models.tables import MarketOrder, TradeLog

logger = logging.getLogger(__name__)


async def _broadcast_market_event(event: str, data: dict):
    """广播交易市场相关的 WS 事件"""
    from ..api.chat import broadcast
    from datetime import datetime, timezone
    await broadcast({
        "type": "system_event",
        "data": {"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), **data},
    })


async def _get_or_create_agent_resource(agent_id: int, resource_type: str, db: AsyncSession) -> AgentResource:
    """获取或创建 agent 个人资源记录（复用 city_service 逻辑，带 frozen_amount 默认值）"""
    result = await db.execute(
        select(AgentResource)
        .where(AgentResource.agent_id == agent_id, AgentResource.resource_type == resource_type)
    )
    ar = result.scalar()
    if not ar:
        ar = AgentResource(agent_id=agent_id, resource_type=resource_type, quantity=0.0, frozen_amount=0.0)
        db.add(ar)
        await db.flush()
    return ar


# ── 挂单 ──────────────────────────────────────────────────

async def create_order(
    seller_id: int, sell_type: str, sell_amount: float,
    buy_type: str, buy_amount: float, *, db: AsyncSession,
) -> dict:
    """创建挂单：冻结卖出资源"""
    if sell_amount <= 0 or buy_amount <= 0:
        return {"ok": False, "reason": "数量必须大于 0"}
    if sell_type == buy_type:
        return {"ok": False, "reason": "卖出和买入不能是同一种资源"}

    ar = await _get_or_create_agent_resource(seller_id, sell_type, db)
    available = ar.quantity - ar.frozen_amount
    if available < sell_amount:
        return {"ok": False, "reason": f"{sell_type} 可用不足，当前可用 {available}，需要 {sell_amount}"}

    # 冻结资源
    ar.quantity -= sell_amount
    ar.frozen_amount += sell_amount

    order = MarketOrder(
        seller_id=seller_id,
        sell_type=sell_type, sell_amount=sell_amount,
        buy_type=buy_type, buy_amount=buy_amount,
        remain_sell_amount=sell_amount, remain_buy_amount=buy_amount,
        status="open",
    )
    db.add(order)
    await db.flush()

    await _broadcast_market_event("order_created", {
        "order_id": order.id, "seller_id": seller_id,
        "sell_type": sell_type, "sell_amount": sell_amount,
        "buy_type": buy_type, "buy_amount": buy_amount,
    })

    await db.commit()
    return {"ok": True, "order_id": order.id}


# ── 接单 ──────────────────────────────────────────────────

async def accept_order(
    buyer_id: int, order_id: int, buy_ratio: float, *, db: AsyncSession,
) -> dict:
    """接单（支持部分购买）：buy_ratio 0~1 表示接多少比例"""
    if buy_ratio <= 0 or buy_ratio > 1.0:
        return {"ok": False, "reason": "buy_ratio 必须在 (0, 1] 之间"}

    # 加锁读取订单（SQLite 单写者天然串行，Postgres 需 FOR UPDATE）
    result = await db.execute(
        select(MarketOrder).where(MarketOrder.id == order_id).with_for_update()
    )
    order = result.scalar()
    if not order:
        return {"ok": False, "reason": "订单不存在"}
    if order.status not in ("open", "partial"):
        return {"ok": False, "reason": f"订单状态为 {order.status}，无法接单"}
    if order.seller_id == buyer_id:
        return {"ok": False, "reason": "不能接自己的单"}

    # 计算本次成交量
    trade_sell = round(order.remain_sell_amount * buy_ratio, 2)
    trade_buy = round(order.remain_buy_amount * buy_ratio, 2)

    if trade_sell <= 0 or trade_buy <= 0:
        return {"ok": False, "reason": "成交量过小"}

    # 检查 buyer 资源（扣除冻结量）
    buyer_res = await _get_or_create_agent_resource(buyer_id, order.buy_type, db)
    buyer_available = buyer_res.quantity - buyer_res.frozen_amount
    if buyer_available < trade_buy:
        return {"ok": False, "reason": f"{order.buy_type} 不足，当前可用 {buyer_available}，需要 {trade_buy}"}

    # 执行交换
    # 1. seller 冻结释放 trade_sell
    seller_sell_res = await _get_or_create_agent_resource(order.seller_id, order.sell_type, db)
    seller_sell_res.frozen_amount -= trade_sell

    # 2. buyer 获得 trade_sell 的卖出资源
    buyer_get_res = await _get_or_create_agent_resource(buyer_id, order.sell_type, db)
    buyer_get_res.quantity += trade_sell

    # 3. buyer 扣除 trade_buy 的买入资源
    buyer_res.quantity -= trade_buy

    # 4. seller 获得 trade_buy 的买入资源
    seller_buy_res = await _get_or_create_agent_resource(order.seller_id, order.buy_type, db)
    seller_buy_res.quantity += trade_buy

    # 更新订单
    order.remain_sell_amount = round(order.remain_sell_amount - trade_sell, 2)
    order.remain_buy_amount = round(order.remain_buy_amount - trade_buy, 2)
    if order.remain_sell_amount <= 0 or order.remain_buy_amount <= 0:
        order.remain_sell_amount = 0.0
        order.remain_buy_amount = 0.0
        order.status = "filled"
    elif order.remain_sell_amount < 0.01 or order.remain_buy_amount < 0.01:
        # Float 精度兜底：极小残余自动归零
        order.remain_sell_amount = 0.0
        order.remain_buy_amount = 0.0
        order.status = "filled"
    else:
        order.status = "partial"

    # 记录成交日志
    log = TradeLog(
        order_id=order.id, seller_id=order.seller_id, buyer_id=buyer_id,
        sell_type=order.sell_type, sell_amount=trade_sell,
        buy_type=order.buy_type, buy_amount=trade_buy,
    )
    db.add(log)
    await db.flush()

    await _broadcast_market_event("order_traded", {
        "order_id": order.id, "seller_id": order.seller_id, "buyer_id": buyer_id,
        "sell_type": order.sell_type, "sell_amount": trade_sell,
        "buy_type": order.buy_type, "buy_amount": trade_buy,
    })

    await db.commit()
    return {"ok": True, "trade_sell": trade_sell, "trade_buy": trade_buy, "order_status": order.status}


# ── 撤单 ──────────────────────────────────────────────────

async def cancel_order(seller_id: int, order_id: int, *, db: AsyncSession) -> dict:
    """撤单：归还剩余冻结资源"""
    result = await db.execute(
        select(MarketOrder).where(MarketOrder.id == order_id).with_for_update()
    )
    order = result.scalar()
    if not order:
        return {"ok": False, "reason": "订单不存在"}
    if order.seller_id != seller_id:
        return {"ok": False, "reason": "只能撤销自己的订单"}
    if order.status not in ("open", "partial"):
        return {"ok": False, "reason": f"订单状态为 {order.status}，无法撤销"}

    # 归还剩余冻结
    ar = await _get_or_create_agent_resource(seller_id, order.sell_type, db)
    ar.quantity += order.remain_sell_amount
    ar.frozen_amount -= order.remain_sell_amount

    order.status = "cancelled"
    await db.flush()

    await _broadcast_market_event("order_cancelled", {
        "order_id": order.id, "seller_id": seller_id,
    })

    await db.commit()
    return {"ok": True}


# ── 查询 ──────────────────────────────────────────────────

async def list_orders(*, db: AsyncSession, status_filter: list[str] | None = None) -> list[dict]:
    """返回挂单列表，默认只返回 open/partial"""
    statuses = status_filter or ["open", "partial"]
    result = await db.execute(
        select(MarketOrder).where(MarketOrder.status.in_(statuses))
        .order_by(MarketOrder.created_at.desc())
    )
    return [
        {
            "id": o.id, "seller_id": o.seller_id,
            "sell_type": o.sell_type, "sell_amount": o.sell_amount,
            "buy_type": o.buy_type, "buy_amount": o.buy_amount,
            "remain_sell_amount": o.remain_sell_amount, "remain_buy_amount": o.remain_buy_amount,
            "status": o.status, "created_at": str(o.created_at),
        }
        for o in result.scalars().all()
    ]


async def get_trade_logs(*, db: AsyncSession, limit: int = 20, offset: int = 0) -> list[dict]:
    """返回成交日志"""
    result = await db.execute(
        select(TradeLog).order_by(TradeLog.created_at.desc()).offset(offset).limit(limit)
    )
    return [
        {
            "id": t.id, "order_id": t.order_id,
            "seller_id": t.seller_id, "buyer_id": t.buyer_id,
            "sell_type": t.sell_type, "sell_amount": t.sell_amount,
            "buy_type": t.buy_type, "buy_amount": t.buy_amount,
            "created_at": str(t.created_at),
        }
        for t in result.scalars().all()
    ]

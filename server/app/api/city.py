"""
城市经济 REST API

GET    /cities/{city}/overview                    — 城市总览
GET    /cities/{city}/buildings                   — 建筑列表
GET    /cities/{city}/buildings/{id}              — 建筑详情
POST   /cities/{city}/buildings/{id}/workers      — 分配工人
DELETE /cities/{city}/buildings/{id}/workers/{aid} — 移除工人
GET    /cities/{city}/resources                   — 资源列表
POST   /agents/{agent_id}/eat                     — 吃饭
GET    /cities/{city}/production-logs             — 生产日志
GET    /agents/{agent_id}/resources               — agent 个人资源
GET    /agents/{agent_id}/attributes              — agent 三维属性
POST   /agents/transfer-resource                  — 资源转移
POST   /cities/{city}/production-tick             — [dev] 触发生产
POST   /cities/{city}/daily-decay                 — [dev] 触发每日属性结算
GET    /market/orders                             — 交易市场挂单列表
POST   /market/orders                             — 创建挂单
POST   /market/orders/{id}/accept                 — 接单
POST   /market/orders/{id}/cancel                 — 撤单
GET    /market/trade-logs                         — 成交日志
"""
import math
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from ..core import get_db
from ..services.city_service import (
    get_city_overview, get_buildings, get_building_detail,
    assign_worker, remove_worker, get_resources, eat_food, get_production_logs,
    get_agent_resources, transfer_resource, production_tick, daily_attribute_decay,
)
from ..services.market_service import (
    create_order, accept_order, cancel_order, list_orders, get_trade_logs,
)

router = APIRouter(tags=["city"])


class WorkerRequest(BaseModel):
    agent_id: int


class TransferRequest(BaseModel):
    from_agent_id: int
    to_agent_id: int
    resource_type: str
    quantity: int


@router.get("/cities/{city}/overview")
async def city_overview(city: str, db: AsyncSession = Depends(get_db)):
    return await get_city_overview(city, db)


@router.get("/cities/{city}/buildings")
async def buildings_list(city: str, db: AsyncSession = Depends(get_db)):
    return await get_buildings(city, db)


@router.get("/cities/{city}/buildings/{building_id}")
async def building_detail(city: str, building_id: int, db: AsyncSession = Depends(get_db)):
    result = await get_building_detail(city, building_id, db)
    if not result:
        raise HTTPException(404, "建筑不存在")
    return result


@router.post("/cities/{city}/buildings/{building_id}/workers")
async def add_worker(city: str, building_id: int, req: WorkerRequest, db: AsyncSession = Depends(get_db)):
    return await assign_worker(city, building_id, req.agent_id, db)


@router.delete("/cities/{city}/buildings/{building_id}/workers/{agent_id}")
async def del_worker(city: str, building_id: int, agent_id: int, db: AsyncSession = Depends(get_db)):
    return await remove_worker(city, building_id, agent_id, db)


@router.get("/cities/{city}/resources")
async def resources_list(city: str, db: AsyncSession = Depends(get_db)):
    return await get_resources(city, db)


@router.post("/agents/{agent_id}/eat")
async def agent_eat(agent_id: int, db: AsyncSession = Depends(get_db)):
    return await eat_food(agent_id, db)


@router.get("/cities/{city}/production-logs")
async def production_logs(city: str, limit: int = Query(20, ge=1, le=100), db: AsyncSession = Depends(get_db)):
    return await get_production_logs(city, limit, db)


@router.get("/agents/{agent_id}/resources")
async def agent_resources(agent_id: int, db: AsyncSession = Depends(get_db)):
    return await get_agent_resources(agent_id, db)


@router.get("/agents/{agent_id}/attributes")
async def agent_attributes(agent_id: int, db: AsyncSession = Depends(get_db)):
    from ..models import Agent
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent 不存在")
    return {"satiety": agent.satiety, "mood": agent.mood, "stamina": agent.stamina}


@router.post("/agents/transfer-resource")
async def transfer(req: TransferRequest, db: AsyncSession = Depends(get_db)):
    return await transfer_resource(req.from_agent_id, req.to_agent_id, req.resource_type, req.quantity, db)


@router.post("/cities/{city}/production-tick")
async def trigger_production(city: str, db: AsyncSession = Depends(get_db)):
    """[dev] 手动触发一次生产循环"""
    await production_tick(city, db)
    return {"ok": True}


@router.post("/cities/{city}/daily-decay")
async def trigger_daily_decay(city: str, db: AsyncSession = Depends(get_db)):
    """[dev] 手动触发一次每日属性结算"""
    await daily_attribute_decay(db)
    return {"ok": True}


# ── 交易市场 ──────────────────────────────────────────────
# TODO: 当前 seller_id / buyer_id 由客户端自报，上线前需接入认证中间件从 token 提取身份

def _check_finite(v: float, field_name: str) -> float:
    if math.isnan(v) or math.isinf(v):
        raise ValueError(f"{field_name} 不能为 NaN 或 Infinity")
    return v


class CreateOrderRequest(BaseModel):
    seller_id: int
    sell_type: str
    sell_amount: float = Field(gt=0)
    buy_type: str
    buy_amount: float = Field(gt=0)

    @field_validator("sell_amount", "buy_amount")
    @classmethod
    def finite_check(cls, v, info):
        return _check_finite(v, info.field_name)


class AcceptOrderRequest(BaseModel):
    buyer_id: int
    buy_ratio: float = Field(1.0, gt=0, le=1)

    @field_validator("buy_ratio")
    @classmethod
    def finite_check(cls, v, info):
        return _check_finite(v, info.field_name)


class CancelOrderRequest(BaseModel):
    seller_id: int


def _map_error_status(reason: str) -> int:
    if "不存在" in reason:
        return 404
    if "不能" in reason or "只能" in reason or "已" in reason or "不足" in reason:
        return 409
    return 400


@router.get("/market/orders")
async def market_orders(status: list[str] | None = Query(None), db: AsyncSession = Depends(get_db)):
    return await list_orders(db=db, status_filter=status)


@router.post("/market/orders")
async def create_market_order(req: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    result = await create_order(
        req.seller_id, req.sell_type, req.sell_amount,
        req.buy_type, req.buy_amount, db=db,
    )
    if not result["ok"]:
        raise HTTPException(_map_error_status(result["reason"]), result["reason"])
    return result


@router.post("/market/orders/{order_id}/accept")
async def accept_market_order(order_id: int, req: AcceptOrderRequest, db: AsyncSession = Depends(get_db)):
    result = await accept_order(req.buyer_id, order_id, req.buy_ratio, db=db)
    if not result["ok"]:
        raise HTTPException(_map_error_status(result["reason"]), result["reason"])
    return result


@router.post("/market/orders/{order_id}/cancel")
async def cancel_market_order(order_id: int, req: CancelOrderRequest, db: AsyncSession = Depends(get_db)):
    result = await cancel_order(req.seller_id, order_id, db=db)
    if not result["ok"]:
        raise HTTPException(_map_error_status(result["reason"]), result["reason"])
    return result


@router.get("/market/trade-logs")
async def market_trade_logs(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await get_trade_logs(db=db, limit=limit, offset=offset)

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
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ..core import get_db
from ..services.city_service import (
    get_city_overview, get_buildings, get_building_detail,
    assign_worker, remove_worker, get_resources, eat_food, get_production_logs,
    get_agent_resources, transfer_resource, production_tick, daily_attribute_decay,
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

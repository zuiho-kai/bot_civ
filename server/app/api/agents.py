from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import secrets
from ..core import get_db
from ..models import Agent
from .schemas import AgentCreate, AgentUpdate, AgentOut

router = APIRouter(prefix="/agents", tags=["agents"])


def generate_bot_token() -> str:
    """生成 oc_ 前缀的 bot token"""
    return f"oc_{secrets.token_hex(24)}"


@router.get("/", response_model=list[AgentOut])
async def list_agents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Agent).where(Agent.id != 0))
    return result.scalars().all()


@router.post("/", response_model=AgentOut, status_code=201)
async def create_agent(data: AgentCreate, db: AsyncSession = Depends(get_db)):
    # 检查名称唯一性
    existing = await db.execute(select(Agent).where(Agent.name == data.name))
    if existing.scalar_one_or_none():
        raise HTTPException(409, f"Agent name '{data.name}' already exists")

    agent = Agent(name=data.name, persona=data.persona, model=data.model, avatar=data.avatar,
                  bot_token=generate_bot_token())
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@router.get("/{agent_id}", response_model=AgentOut)
async def get_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    return agent


@router.put("/{agent_id}", response_model=AgentOut)
async def update_agent(agent_id: int, data: AgentUpdate, db: AsyncSession = Depends(get_db)):
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    if agent_id == 0:
        raise HTTPException(403, "Cannot modify the Human agent")

    update_data = data.model_dump(exclude_unset=True)

    # 如果改名，检查唯一性
    if "name" in update_data and update_data["name"] != agent.name:
        existing = await db.execute(select(Agent).where(Agent.name == update_data["name"]))
        if existing.scalar_one_or_none():
            raise HTTPException(409, f"Agent name '{update_data['name']}' already exists")

    for field, value in update_data.items():
        setattr(agent, field, value)

    await db.commit()
    await db.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(agent_id: int, db: AsyncSession = Depends(get_db)):
    if agent_id == 0:
        raise HTTPException(403, "Cannot delete the Human agent")
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    await db.delete(agent)
    await db.commit()


@router.post("/{agent_id}/regenerate-token", response_model=AgentOut)
async def regenerate_token(agent_id: int, db: AsyncSession = Depends(get_db)):
    if agent_id == 0:
        raise HTTPException(403, "Human agent does not have a bot token")
    agent = await db.get(Agent, agent_id)
    if not agent:
        raise HTTPException(404, "Agent not found")
    agent.bot_token = generate_bot_token()
    await db.commit()
    await db.refresh(agent)
    return agent

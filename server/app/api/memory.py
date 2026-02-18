"""记忆管理 REST API"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from ..core import get_db
from ..services.memory_admin_service import (
    list_memories, get_memory_detail, get_agent_memory_stats, get_message_memory_refs,
    create_memory, update_memory, delete_memory,
)

router = APIRouter(prefix="/memories", tags=["memory"])


class CreateMemoryRequest(BaseModel):
    agent_id: int
    memory_type: str
    content: str


class UpdateMemoryRequest(BaseModel):
    content: str | None = None
    memory_type: str | None = None


@router.get("")
async def api_list_memories(
    agent_id: int | None = Query(None),
    memory_type: str | None = Query(None),
    keyword: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    return await list_memories(agent_id, memory_type, keyword, page, page_size, db)


@router.post("")
async def api_create_memory(
    req: CreateMemoryRequest,
    db: AsyncSession = Depends(get_db),
):
    return await create_memory(req.agent_id, req.memory_type, req.content, db)


@router.get("/stats")
async def api_memory_stats(
    agent_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await get_agent_memory_stats(agent_id, db)


@router.get("/{memory_id}")
async def api_memory_detail(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await get_memory_detail(memory_id, db)
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


@router.put("/{memory_id}")
async def api_update_memory(
    memory_id: int,
    req: UpdateMemoryRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await update_memory(memory_id, req.content, req.memory_type, db)
    if not result:
        raise HTTPException(status_code=404, detail="Memory not found")
    return result


@router.delete("/{memory_id}")
async def api_delete_memory(
    memory_id: int,
    db: AsyncSession = Depends(get_db),
):
    ok = await delete_memory(memory_id, db)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
    return {"ok": True}


@router.get("/messages/{message_id}/memory-refs")
async def api_message_memory_refs(
    message_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await get_message_memory_refs(message_id, db)

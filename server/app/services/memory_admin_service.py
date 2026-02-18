"""记忆管理服务 — 供 REST API 使用的查询/统计功能"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from ..models import Memory, MemoryReference


async def list_memories(
    agent_id: int | None, memory_type: str | None,
    keyword: str | None,
    page: int, page_size: int, db: AsyncSession,
) -> dict:
    """分页查询记忆列表"""
    q = select(Memory)
    if agent_id is not None:
        q = q.where(Memory.agent_id == agent_id)
    if memory_type is not None:
        q = q.where(Memory.memory_type == memory_type)
    if keyword:
        q = q.where(Memory.content.ilike(f"%{keyword}%"))
    q = q.order_by(Memory.created_at.desc())

    # 总数
    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # 分页
    q = q.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(q)
    items = [
        {
            "id": m.id, "agent_id": m.agent_id,
            "memory_type": m.memory_type, "content": m.content,
            "access_count": m.access_count,
            "expires_at": str(m.expires_at) if m.expires_at else None,
            "created_at": str(m.created_at),
        }
        for m in result.scalars().all()
    ]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


async def get_memory_detail(memory_id: int, db: AsyncSession) -> dict | None:
    """获取单条记忆详情"""
    m = await db.get(Memory, memory_id)
    if not m:
        return None
    return {
        "id": m.id, "agent_id": m.agent_id,
        "memory_type": m.memory_type, "content": m.content,
        "access_count": m.access_count,
        "expires_at": str(m.expires_at) if m.expires_at else None,
        "created_at": str(m.created_at),
    }


async def get_message_memory_refs(message_id: int, db: AsyncSession) -> list[dict]:
    """获取某条消息引用的记忆列表"""
    result = await db.execute(
        select(MemoryReference, Memory)
        .join(Memory, MemoryReference.memory_id == Memory.id)
        .where(MemoryReference.message_id == message_id)
    )
    return [
        {
            "memory_id": ref.memory_id,
            "content": mem.content,
            "memory_type": mem.memory_type,
            "created_at": str(ref.created_at),
        }
        for ref, mem in result.all()
    ]


async def get_agent_memory_stats(agent_id: int | None, db: AsyncSession) -> dict:
    """获取 Agent 记忆统计（agent_id=None 时返回全局统计）"""
    q = select(Memory.memory_type, func.count()).group_by(Memory.memory_type)
    if agent_id is not None:
        q = q.where(Memory.agent_id == agent_id)
    result = await db.execute(q)
    stats = {row[0]: row[1] for row in result.all()}
    total = sum(stats.values())
    return {"agent_id": agent_id, "total": total, "by_type": stats}


async def create_memory(
    agent_id: int, memory_type: str, content: str, db: AsyncSession,
) -> dict:
    """手动创建一条记忆"""
    m = Memory(agent_id=agent_id, memory_type=memory_type, content=content)
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return {
        "id": m.id, "agent_id": m.agent_id,
        "memory_type": m.memory_type, "content": m.content,
        "access_count": m.access_count,
        "expires_at": str(m.expires_at) if m.expires_at else None,
        "created_at": str(m.created_at),
    }


async def update_memory(
    memory_id: int, content: str | None, memory_type: str | None, db: AsyncSession,
) -> dict | None:
    """更新记忆内容/类型"""
    m = await db.get(Memory, memory_id)
    if not m:
        return None
    if content is not None:
        m.content = content
    if memory_type is not None:
        m.memory_type = memory_type
    await db.commit()
    await db.refresh(m)
    return {
        "id": m.id, "agent_id": m.agent_id,
        "memory_type": m.memory_type, "content": m.content,
        "access_count": m.access_count,
        "expires_at": str(m.expires_at) if m.expires_at else None,
        "created_at": str(m.created_at),
    }


async def delete_memory(memory_id: int, db: AsyncSession) -> bool:
    """删除一条记忆，返回是否成功"""
    m = await db.get(Memory, memory_id)
    if not m:
        return False
    await db.delete(m)
    await db.commit()
    return True

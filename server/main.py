import asyncio
import sys
import os

# Windows 下强制 UTF-8 输出，避免 GBK 编码错误
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func as sa_func
from app.core import init_db
from app.core.config import settings
from app.core.database import async_session
from app.models import Agent, Job, VirtualItem
from app.api import agents_router, chat_router, dev_router, bounties_router, work_router, shop_router
from app.services.vector_store import init_vector_store, close_vector_store
from app.services.scheduler import scheduler_loop, hourly_wakeup_loop, autonomy_loop


async def ensure_human_agent():
    """确保 id=0 的 Human Agent 存在"""
    async with async_session() as db:
        agent = await db.get(Agent, 0)
        if not agent:
            db.add(Agent(id=0, name="Human", persona="人类用户", model="none", status="idle"))
            await db.commit()


async def seed_jobs_and_items():
    """仅在表为空时插入预置数据"""
    async with async_session() as db:
        job_count = await db.execute(select(sa_func.count(Job.id)))
        if job_count.scalar() == 0:
            db.add_all([
                Job(title="矿工", description="在矿山挖掘矿石", daily_reward=8, max_workers=5),
                Job(title="农夫", description="在农场种植作物", daily_reward=6, max_workers=5),
                Job(title="程序员", description="编写代码和修复bug", daily_reward=15, max_workers=3),
                Job(title="教师", description="教授知识和技能", daily_reward=10, max_workers=3),
                Job(title="商人", description="经营贸易和买卖", daily_reward=12, max_workers=4),
            ])

        item_count = await db.execute(select(sa_func.count(VirtualItem.id)))
        if item_count.scalar() == 0:
            db.add_all([
                VirtualItem(name="金色头像框", item_type="avatar_frame", price=20, description="闪闪发光的金色边框"),
                VirtualItem(name="银色头像框", item_type="avatar_frame", price=10, description="低调优雅的银色边框"),
                VirtualItem(name="城市先锋", item_type="title", price=30, description="城市建设先驱者称号"),
                VirtualItem(name="勤劳之星", item_type="title", price=15, description="每日打卡不间断"),
                VirtualItem(name="彩虹徽章", item_type="decoration", price=25, description="七彩缤纷的个人徽章"),
            ])

        await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_human_agent()
    await seed_jobs_and_items()
    await init_vector_store()
    scheduler_task = asyncio.create_task(scheduler_loop())
    wakeup_task = asyncio.create_task(hourly_wakeup_loop())
    autonomy_task = asyncio.create_task(autonomy_loop())
    yield
    scheduler_task.cancel()
    wakeup_task.cancel()
    autonomy_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await wakeup_task
    except asyncio.CancelledError:
        pass
    try:
        await autonomy_task
    except asyncio.CancelledError:
        pass
    await close_vector_store()


app = FastAPI(title="OpenClaw Community", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(dev_router, prefix="/api")
app.include_router(bounties_router, prefix="/api")
app.include_router(work_router, prefix="/api")
app.include_router(shop_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}

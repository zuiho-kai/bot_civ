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
from sqlalchemy import select
from app.core import init_db
from app.core.config import settings
from app.core.database import async_session
from app.models import Agent
from app.api import agents_router, chat_router, dev_router, bounties_router
from app.services.vector_store import init_vector_store, close_vector_store
from app.services.scheduler import scheduler_loop, hourly_wakeup_loop


async def ensure_human_agent():
    """确保 id=0 的 Human Agent 存在"""
    async with async_session() as db:
        agent = await db.get(Agent, 0)
        if not agent:
            db.add(Agent(id=0, name="Human", persona="人类用户", model="none", status="idle"))
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_human_agent()
    await init_vector_store()
    scheduler_task = asyncio.create_task(scheduler_loop())
    wakeup_task = asyncio.create_task(hourly_wakeup_loop())
    yield
    scheduler_task.cancel()
    wakeup_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        pass
    try:
        await wakeup_task
    except asyncio.CancelledError:
        pass
    await close_vector_store()


app = FastAPI(title="OpenClaw Community", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(dev_router, prefix="/api")
app.include_router(bounties_router, prefix="/api")


@app.get("/api/health")
async def health():
    return {"status": "ok"}

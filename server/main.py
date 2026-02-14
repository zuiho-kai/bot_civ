from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from app.core import init_db
from app.core.database import async_session
from app.models import Agent
from app.api import agents_router, chat_router, dev_router


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
    yield


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


@app.get("/api/health")
async def health():
    return {"status": "ok"}

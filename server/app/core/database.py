from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from pathlib import Path
from .config import settings


# 确保 data 目录存在
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(f"sqlite+aiosqlite:///{settings.db_path}", echo=settings.debug)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def _migrate_bot_token(conn):
    """M1.5 迁移：给 agents 表加 bot_token 字段（如果不存在）"""
    result = await conn.execute(text("PRAGMA table_info(agents)"))
    columns = [row[1] for row in result.fetchall()]
    if "bot_token" not in columns:
        await conn.execute(text("ALTER TABLE agents ADD COLUMN bot_token VARCHAR(64)"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_bot_token(conn)


async def get_db():
    async with async_session() as session:
        yield session

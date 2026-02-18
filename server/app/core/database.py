from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text, event
from pathlib import Path
from .config import settings


# 确保 data 目录存在
Path(settings.db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(
    f"sqlite+aiosqlite:///{settings.db_path}",
    echo=settings.debug,
)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):
    """启用 WAL 模式和 BEGIN IMMEDIATE"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()
    # 设置为 IMMEDIATE 模式，所有事务都用 BEGIN IMMEDIATE
    dbapi_connection.isolation_level = "IMMEDIATE"


async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def _migrate_bot_token(conn):
    """M1.5 迁移：给 agents 表加 bot_token 字段（如果不存在）"""
    result = await conn.execute(text("PRAGMA table_info(agents)"))
    columns = [row[1] for row in result.fetchall()]
    if "bot_token" not in columns:
        await conn.execute(text("ALTER TABLE agents ADD COLUMN bot_token VARCHAR(64)"))


async def _migrate_satiety_mood(conn):
    """M5 迁移：给 agents 表加 satiety/mood/stamina 字段"""
    result = await conn.execute(text("PRAGMA table_info(agents)"))
    columns = [row[1] for row in result.fetchall()]
    if "satiety" not in columns:
        await conn.execute(text("ALTER TABLE agents ADD COLUMN satiety INTEGER DEFAULT 100"))
    if "mood" not in columns:
        await conn.execute(text("ALTER TABLE agents ADD COLUMN mood INTEGER DEFAULT 80"))
    if "stamina" not in columns:
        await conn.execute(text("ALTER TABLE agents ADD COLUMN stamina INTEGER DEFAULT 100"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _migrate_bot_token(conn)
        await _migrate_satiety_mood(conn)


async def get_db():
    async with async_session() as session:
        yield session

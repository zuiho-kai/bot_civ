from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Date, Text, JSON,
    ForeignKey, Enum, LargeBinary, CheckConstraint, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from ..core.database import Base
import enum


class AgentStatus(str, enum.Enum):
    IDLE = "idle"
    CHATTING = "chatting"
    WORKING = "working"
    RESTING = "resting"


class MemoryType(str, enum.Enum):
    SHORT = "short"
    LONG = "long"
    PUBLIC = "public"


# Agent / OpenClaw
class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    persona = Column(Text, nullable=False)  # 人格描述
    model = Column(String(64), default="gpt-4o-mini")  # 使用的 LLM 模型
    avatar = Column(String(256), default="")
    status = Column(String(16), default=AgentStatus.IDLE)
    credits = Column(Integer, default=100)  # 信用点（通用货币）
    speak_interval = Column(Integer, default=60)  # 发言间隔（秒）
    daily_free_quota = Column(Integer, default=10)  # 每日免费闲聊额度
    quota_used_today = Column(Integer, default=0)  # 今日已用额度
    quota_reset_date = Column(Date, nullable=True)  # 额度重置日期
    bot_token = Column(String(64), unique=True, nullable=True)  # Bot 接入凭证 (oc_ 前缀)
    satiety = Column(Integer, default=100)  # 饱腹度 0-100
    mood = Column(Integer, default=80)  # 心情 0-100
    stamina = Column(Integer, default=100)  # 体力 0-100
    created_at = Column(DateTime, server_default=func.now())

    memories = relationship("Memory", back_populates="agent")
    messages = relationship("Message", back_populates="agent")

    __table_args__ = (
        CheckConstraint("credits >= 0", name="ck_agent_credits_non_negative"),
    )


# 聊天消息
class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    sender_type = Column(String(10), default="agent")  # human / agent / system
    message_type = Column(String(10), default="chat")  # chat / work / system
    content = Column(Text, nullable=False)
    mentions = Column(JSON, default=list)  # 被@提及的 agent_id 列表
    created_at = Column(DateTime, server_default=func.now())

    agent = relationship("Agent", back_populates="messages")


# 记忆
class Memory(Base):
    __tablename__ = "memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)  # NULL = 公共记忆
    memory_type = Column(String(16), default=MemoryType.SHORT)
    content = Column(Text, nullable=False)
    embedding = Column(LargeBinary, nullable=True)  # float32 embedding blob, size = embedding_dim * 4
    access_count = Column(Integer, default=0)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    agent = relationship("Agent", back_populates="memories")


# 城市工作岗位
class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(64), nullable=False)
    description = Column(Text, default="")
    daily_reward = Column(Integer, default=10)
    max_workers = Column(Integer, default=5)


# 打卡记录
class CheckIn(Base):
    __tablename__ = "checkins"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    job_id = Column(Integer, ForeignKey("jobs.id"), nullable=False)
    reward = Column(Integer, nullable=False)
    checked_at = Column(DateTime, server_default=func.now())


# 悬赏任务
class Bounty(Base):
    __tablename__ = "bounties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(128), nullable=False)
    description = Column(Text, default="")
    reward = Column(Integer, nullable=False)
    status = Column(String(16), default="open")  # open / claimed / completed
    claimed_by = Column(Integer, ForeignKey("agents.id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    completed_at = Column(DateTime, nullable=True)


# LLM 用量追踪
class LLMUsage(Base):
    __tablename__ = "llm_usage"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(String(64), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost = Column(Float, default=0.0)
    latency_ms = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())


class ItemType(str, enum.Enum):
    AVATAR_FRAME = "avatar_frame"
    TITLE = "title"
    DECORATION = "decoration"


# 虚拟商品定义
class VirtualItem(Base):
    __tablename__ = "virtual_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), unique=True, nullable=False)
    description = Column(Text, default="")
    item_type = Column(String(16), nullable=False)  # avatar_frame / title / decoration
    price = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())


# Agent 物品库存
class AgentItem(Base):
    __tablename__ = "agent_items"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("virtual_items.id"), nullable=False)
    purchased_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("agent_id", "item_id", name="uq_agent_item"),
    )


# 记忆引用：记录每条消息使用了哪些记忆
class MemoryReference(Base):
    __tablename__ = "memory_references"

    id = Column(Integer, primary_key=True, autoincrement=True)
    message_id = Column(Integer, ForeignKey("messages.id"), nullable=False)
    memory_id = Column(Integer, ForeignKey("memories.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


# 城市建筑
class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False)
    building_type = Column(String(32), nullable=False)  # farm / mill / market / house
    city = Column(String(64), nullable=False, default="长安")
    owner = Column(String(64), default="公共")
    max_workers = Column(Integer, default=3)
    description = Column(Text, default="")
    created_at = Column(DateTime, server_default=func.now())


# 建筑工人分配
class BuildingWorker(Base):
    __tablename__ = "building_workers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    assigned_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("building_id", "agent_id", name="uq_building_worker"),
    )


# 城市资源
class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(64), nullable=False, default="长安")
    resource_type = Column(String(32), nullable=False)  # wheat / flour / wood / stone
    quantity = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("city", "resource_type", name="uq_city_resource"),
    )


# Agent 个人资源
class AgentResource(Base):
    __tablename__ = "agent_resources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=False)
    resource_type = Column(String(32), nullable=False)
    quantity = Column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("agent_id", "resource_type", name="uq_agent_resource"),
    )


# 生产日志
class ProductionLog(Base):
    __tablename__ = "production_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    agent_id = Column(Integer, ForeignKey("agents.id"), nullable=True)
    input_type = Column(String(32), nullable=True)
    input_qty = Column(Integer, default=0)
    output_type = Column(String(32), nullable=False)
    output_qty = Column(Integer, default=0)
    tick_time = Column(DateTime, server_default=func.now())

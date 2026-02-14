from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Date, Text, JSON, ForeignKey, Enum
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
    created_at = Column(DateTime, server_default=func.now())

    memories = relationship("Memory", back_populates="agent")
    messages = relationship("Message", back_populates="agent")


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

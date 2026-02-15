import re
from datetime import datetime
from pydantic import BaseModel, field_validator
from typing import Optional


# --- Agent ---
class AgentCreate(BaseModel):
    name: str
    persona: str
    model: str = "gpt-4o-mini"
    avatar: str = ""

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Agent name cannot be empty")
        if len(v) > 64:
            raise ValueError("Agent name must be 64 characters or less")
        if not re.match(r'^[\w\u4e00-\u9fff]+$', v):
            raise ValueError("Agent name can only contain letters, digits, underscores, and Chinese characters")
        return v


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    persona: Optional[str] = None
    model: Optional[str] = None
    avatar: Optional[str] = None
    status: Optional[str] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Agent name cannot be empty")
        if len(v) > 64:
            raise ValueError("Agent name must be 64 characters or less")
        if not re.match(r'^[\w\u4e00-\u9fff]+$', v):
            raise ValueError("Agent name can only contain letters, digits, underscores, and Chinese characters")
        return v


class AgentOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    name: str
    persona: str
    model: str
    avatar: str
    status: str
    credits: int
    speak_interval: int
    daily_free_quota: int
    quota_used_today: int
    bot_token: str | None = None


# --- Message ---
class MessageOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    agent_id: int
    agent_name: str = ""
    sender_type: str = "agent"
    message_type: str = "chat"
    content: str
    mentions: list[int] = []
    created_at: str


# --- Chat WebSocket ---
class WsChatMessage(BaseModel):
    """客户端 → 服务端的 WebSocket 消息"""
    type: str = "chat_message"
    content: str
    message_type: str = "chat"  # chat / work


# --- Bounty ---
class BountyCreate(BaseModel):
    title: str
    description: str = ""
    reward: int

    @field_validator("title")
    @classmethod
    def validate_title(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Bounty title cannot be empty")
        if len(v) > 128:
            raise ValueError("Bounty title must be 128 characters or less")
        return v

    @field_validator("reward")
    @classmethod
    def reward_must_be_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("reward must be greater than 0")
        if v > 10000:
            raise ValueError("reward must be 10000 or less")
        return v


class BountyOut(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    description: str
    reward: int
    status: str
    claimed_by: Optional[int] = None
    created_at: datetime
    completed_at: Optional[datetime] = None

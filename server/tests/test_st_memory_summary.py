"""M6.2-P1: 记忆提取质量优化 — 系统测试"""
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

CHAT = "app.api.chat"
CONFIG = "app.core.config"


def _make_mock_provider(name="openrouter", available=True):
    p = MagicMock()
    p.name = name
    p.model_id = "test-model"
    p.is_available.return_value = available
    p.get_auth_token.return_value = "fake-token"
    p.get_base_url.return_value = "https://fake.api/v1"
    return p


def _make_mock_entry(providers):
    entry = MagicMock()
    entry.providers = providers
    return entry


# --- AC-4：MODEL_REGISTRY 可配置 ---

def test_st_model_registry_has_memory_summary():
    """AC-4：MODEL_REGISTRY 中存在 memory-summary-model 条目"""
    from app.core.config import MODEL_REGISTRY
    assert "memory-summary-model" in MODEL_REGISTRY
    entry = MODEL_REGISTRY["memory-summary-model"]
    assert len(entry.providers) >= 2  # 至少主 + 备


def test_st_memory_summary_model_hidden_from_frontend():
    """AC-4 补充：memory-summary-model 不暴露给前端"""
    from app.core.config import list_available_models
    models = list_available_models()
    assert all(m["id"] != "memory-summary-model" for m in models)


# --- AC-1：LLM 生成记忆 ---

@pytest.mark.asyncio
async def test_st_memory_content_is_llm_generated():
    """AC-1：正常情况下记忆内容由 LLM 生成，不等于截断格式"""
    from app.api.chat import _extract_memory, _agent_reply_counts, EXTRACT_EVERY

    _agent_reply_counts[900] = EXTRACT_EVERY - 1
    messages = [{"name": f"user{i}", "content": f"重要决定{i}"} for i in range(EXTRACT_EVERY)]

    saved_content = None

    async def capture_save(agent_id, content, mem_type, db):
        nonlocal saved_content
        saved_content = content
        mem = MagicMock()
        mem.id = 1
        return mem

    mock_db = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    choice = MagicMock()
    choice.message.content = "用户做出了多项重要决定，涉及决定0到决定4"
    resp = MagicMock()
    resp.choices = [choice]
    mock_client.chat.completions.create = AsyncMock(return_value=resp)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    provider = _make_mock_provider()
    entry = _make_mock_entry([provider])

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client), \
         patch(f"{CHAT}.async_session", return_value=mock_session), \
         patch(f"{CHAT}.memory_service") as mock_mem_svc:
        mock_mem_svc.save_memory = AsyncMock(side_effect=capture_save)
        await _extract_memory(900, messages)

    assert saved_content is not None
    assert not saved_content.startswith("对话摘要: ")
    assert len(saved_content) <= 100


# --- AC-2：Fallback 链 ---

@pytest.mark.asyncio
async def test_st_fallback_chain_no_error_no_block():
    """AC-2：全部 provider 失败时 fallback 到截断，不报错不阻塞"""
    from app.api.chat import _extract_memory, _agent_reply_counts, EXTRACT_EVERY

    _agent_reply_counts[901] = EXTRACT_EVERY - 1
    messages = [{"name": f"user{i}", "content": f"内容{i}"} for i in range(EXTRACT_EVERY)]

    saved_content = None

    async def capture_save(agent_id, content, mem_type, db):
        nonlocal saved_content
        saved_content = content
        mem = MagicMock()
        mem.id = 1
        return mem

    mock_db = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API down"))
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    provider = _make_mock_provider()
    entry = _make_mock_entry([provider])

    with patch(f"{CONFIG}.MODEL_REGISTRY", {"memory-summary-model": entry}), \
         patch(f"{CHAT}.AsyncOpenAI", return_value=mock_client), \
         patch(f"{CHAT}.async_session", return_value=mock_session), \
         patch(f"{CHAT}.memory_service") as mock_mem_svc:
        mock_mem_svc.save_memory = AsyncMock(side_effect=capture_save)
        await _extract_memory(901, messages)

    assert saved_content is not None
    assert saved_content.startswith("对话摘要: ")


# --- AC-5：fire-and-forget ---

@pytest.mark.asyncio
async def test_st_delayed_send_not_blocked_by_memory():
    """AC-5：delayed_send 中记忆提取为 fire-and-forget，不阻塞消息广播"""
    from app.api.chat import delayed_send

    async def slow_extract(*args, **kwargs):
        await asyncio.sleep(10)

    agent_info = {
        "agent_id": 902,
        "agent_name": "TestAgent",
        "history": [{"name": "user", "content": "hi"}],
    }

    mock_db = AsyncMock()
    mock_session = AsyncMock()
    mock_session.__aenter__ = AsyncMock(return_value=mock_db)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    mock_msg = MagicMock()
    mock_msg.id = 1
    mock_msg.created_at = "2026-01-01"

    with patch(f"{CHAT}._extract_memory", side_effect=slow_extract), \
         patch(f"{CHAT}.async_session", return_value=mock_session), \
         patch(f"{CHAT}.send_agent_message", new_callable=AsyncMock, return_value=mock_msg), \
         patch(f"{CHAT}.economy_service") as mock_econ, \
         patch(f"{CHAT}.MemoryReference"):
        mock_econ.deduct_quota = AsyncMock()
        mock_db.commit = AsyncMock()

        # delayed_send 应在 2s 内返回（不等待 10s 的记忆提取）
        await asyncio.wait_for(
            delayed_send(agent_info, "回复内容", None, 0.0),
            timeout=2.0,
        )

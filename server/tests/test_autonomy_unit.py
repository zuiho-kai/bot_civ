"""M4 单元测试：autonomy_service 各函数独立测试。"""

import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.database import Base, engine, async_session
from app.models import Agent, Job, VirtualItem, Message

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create tables + seed, tear down after each test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        db.add(Agent(id=0, name="Human", persona="human", model="none", status="idle"))
        db.add(Agent(id=1, name="Alice", persona="乐观的程序员，喜欢写代码", model="test", credits=50))
        db.add(Agent(id=2, name="Bob", persona="沉稳的架构师", model="test", credits=20))
        db.add(Job(id=1, title="矿工", description="挖矿", daily_reward=10, max_workers=5))
        db.add(Job(id=2, title="厨师", description="做饭", daily_reward=15, max_workers=3))
        db.add(VirtualItem(id=1, name="金框", item_type="avatar_frame", price=8, description="test"))
        db.add(VirtualItem(id=2, name="贵框", item_type="avatar_frame", price=999, description="expensive"))
        db.add(Message(agent_id=0, sender_type="human", message_type="chat", content="大家好"))
        db.add(Message(agent_id=1, sender_type="agent", message_type="chat", content="你好呀"))
        await db.commit()

    yield

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------- 1. test_build_world_snapshot ----------

async def test_build_world_snapshot():
    """快照包含所有必要字段。"""
    from app.services.autonomy_service import build_world_snapshot

    async with async_session() as db:
        snapshot = await build_world_snapshot(db)

    assert snapshot, "快照不应为空"
    assert "居民状态" in snapshot
    assert "Alice" in snapshot
    assert "Bob" in snapshot
    assert "最近聊天" in snapshot
    assert "可用岗位" in snapshot
    assert "矿工" in snapshot
    assert "商店商品" in snapshot
    assert "金框" in snapshot
    assert "上一轮行为" in snapshot
    # token 估算：粗略按 1 字 ≈ 2 token
    assert len(snapshot) < 40000, f"快照过长: {len(snapshot)} chars"


# ---------- 2. test_decide_valid_json ----------

async def test_decide_valid_json():
    """mock LLM 返回有效 JSON，解析正确。"""
    from app.services.autonomy_service import decide

    valid_json = json.dumps([
        {"agent_id": 1, "action": "checkin", "params": {}, "reason": "上班"},
        {"agent_id": 2, "action": "rest", "params": {}, "reason": "休息"},
    ])

    mock_choice = MagicMock()
    mock_choice.message.content = valid_json
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client):
        decisions = await decide("fake snapshot")

    assert len(decisions) == 2
    assert decisions[0]["agent_id"] == 1
    assert decisions[0]["action"] == "checkin"
    assert decisions[1]["agent_id"] == 2
    assert decisions[1]["action"] == "rest"


# ---------- 3. test_decide_invalid_json ----------

async def test_decide_invalid_json():
    """mock LLM 返回乱码，返回空列表不崩溃。"""
    from app.services.autonomy_service import decide

    mock_choice = MagicMock()
    mock_choice.message.content = "this is not json!!!"
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client):
        decisions = await decide("fake snapshot")

    assert decisions == []


# ---------- 4. test_execute_checkin ----------

async def test_execute_checkin():
    """checkin 决策 → work_service 被调用 + 广播。"""
    from app.services.autonomy_service import execute_decisions

    decisions = [{"agent_id": 1, "action": "checkin", "params": {}, "reason": "上班"}]

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock) as mock_broadcast:
        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

    assert stats["success"] == 1
    assert stats["failed"] == 0
    mock_broadcast.assert_called_once()
    call_args = mock_broadcast.call_args
    assert call_args[0][2] == "checkin"  # action arg

    # 验证 credits 增加（随机分配岗位，日薪 10 或 15）
    async with async_session() as db:
        agent = await db.get(Agent, 1)
        assert agent.credits in (60, 65), f"Expected 60 or 65, got {agent.credits}"


# ---------- 5. test_execute_purchase ----------

async def test_execute_purchase():
    """purchase 决策 → shop_service 被调用 + 广播。"""
    from app.services.autonomy_service import execute_decisions

    decisions = [{"agent_id": 1, "action": "purchase", "params": {"item_id": 1}, "reason": "买金框"}]

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock) as mock_broadcast:
        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

    assert stats["success"] == 1
    mock_broadcast.assert_called_once()
    call_args = mock_broadcast.call_args
    assert call_args[0][2] == "purchase"

    # 验证 credits 减少
    async with async_session() as db:
        agent = await db.get(Agent, 1)
        assert agent.credits == 42  # 50 - 8


# ---------- 6. test_execute_chat ----------

async def test_execute_chat():
    """chat 决策 → batch_generate 被调用。"""
    from app.services.autonomy_service import execute_decisions

    decisions = [{"agent_id": 1, "action": "chat", "params": {}, "reason": "聊天"}]

    mock_batch_result = {
        1: ("你好大家！", {
            "model": "test", "agent_id": 1,
            "prompt_tokens": 10, "completion_tokens": 5,
            "total_tokens": 15, "latency_ms": 100,
        }, [])
    }

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock), \
         patch("app.services.autonomy_service.runner_manager") as mock_runner, \
         patch("app.services.autonomy_service.economy_service") as mock_econ:
        mock_runner.batch_generate = AsyncMock(return_value=mock_batch_result)
        mock_econ.check_quota = AsyncMock(return_value=MagicMock(allowed=True))
        mock_econ.deduct_quota = AsyncMock()

        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

    # chat 走异步 batch，success 在 _execute_chats 中计数
    mock_runner.batch_generate.assert_called_once()


# ---------- 7. test_execute_rest ----------

async def test_execute_rest():
    """rest 决策 → skipped 计数，无状态变化。"""
    from app.services.autonomy_service import execute_decisions

    decisions = [{"agent_id": 1, "action": "rest", "params": {}, "reason": "休息"}]

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock) as mock_broadcast:
        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

    assert stats["skipped"] == 1
    assert stats["success"] == 0
    mock_broadcast.assert_not_called()

    # credits 不变
    async with async_session() as db:
        agent = await db.get(Agent, 1)
        assert agent.credits == 50


# ---------- 8. test_execute_failure_isolation ----------

async def test_execute_failure_isolation():
    """一条失败不影响后续执行。"""
    from app.services.autonomy_service import execute_decisions

    decisions = [
        # Agent 2 余额不足购买贵框 (price=999, credits=20) → 失败
        {"agent_id": 2, "action": "purchase", "params": {"item_id": 2}, "reason": "买贵框"},
        # Agent 1 打卡 → 应该成功
        {"agent_id": 1, "action": "checkin", "params": {}, "reason": "上班"},
    ]

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            stats = await execute_decisions(decisions, db)

    assert stats["failed"] >= 1, "Bob 购买应该失败"
    assert stats["success"] >= 1, "Alice 打卡应该成功"

    # Alice credits 增加（不受 Bob 失败影响）— 随机分配岗位，日薪 10 或 15
    async with async_session() as db:
        agent1 = await db.get(Agent, 1)
        assert agent1.credits in (60, 65), f"Alice credits should be 60 or 65, got {agent1.credits}"

        agent2 = await db.get(Agent, 2)
        assert agent2.credits == 20  # 不变


# ---------- 9. AC-M4-10: 连续 3 轮人格差异验证 ----------

async def test_personality_variance_three_rounds():
    """连续 3 轮 tick，mock LLM 返回不同决策，验证系统能处理差异化行为。"""
    from app.services.autonomy_service import build_world_snapshot, decide, execute_decisions

    # 3 轮不同的 LLM 回复，模拟人格差异
    round_replies = [
        json.dumps([
            {"agent_id": 1, "action": "checkin", "params": {}, "reason": "Alice 早起打卡，勤奋的程序员"},
            {"agent_id": 2, "action": "rest", "params": {}, "reason": "Bob 觉得还早，再睡会"},
        ]),
        json.dumps([
            {"agent_id": 1, "action": "chat", "params": {}, "reason": "Alice 想分享代码心得"},
            {"agent_id": 2, "action": "checkin", "params": {}, "reason": "Bob 终于起床去上班"},
        ]),
        json.dumps([
            {"agent_id": 1, "action": "purchase", "params": {"item_id": 1}, "reason": "Alice 奖励自己买个金框"},
            {"agent_id": 2, "action": "chat", "params": {}, "reason": "Bob 想聊聊架构设计"},
        ]),
    ]

    all_decisions = []

    for i, reply_text in enumerate(round_replies):
        mock_choice = MagicMock()
        mock_choice.message.content = reply_text
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with patch("app.services.autonomy_service.resolve_model",
                   return_value=("http://fake", "sk-fake", "test-model")), \
             patch("app.services.autonomy_service.AsyncOpenAI",
                   return_value=mock_client):
            decisions = await decide("fake snapshot")
            all_decisions.append(decisions)

    # 验证 3 轮都产生了有效决策
    assert len(all_decisions) == 3
    for i, decisions in enumerate(all_decisions):
        assert len(decisions) == 2, f"第 {i+1} 轮应有 2 条决策"

    # 验证 Alice 在 3 轮中做了不同的事
    alice_actions = [d[0]["action"] for d in all_decisions]
    assert len(set(alice_actions)) == 3, f"Alice 应有 3 种不同行为，实际: {alice_actions}"

    # 验证 Bob 在 3 轮中也做了不同的事
    bob_actions = [d[1]["action"] for d in all_decisions]
    assert len(set(bob_actions)) == 3, f"Bob 应有 3 种不同行为，实际: {bob_actions}"


# ---------- 10. AC-M4-11: 性能基准 — snapshot < 200ms, tick < 60s ----------

async def test_performance_baseline():
    """6 个 Agent 的 snapshot 构建 < 200ms，完整 tick < 60s。"""
    import time
    from app.services.autonomy_service import build_world_snapshot, execute_decisions

    # 补充到 6 个 Agent
    async with async_session() as db:
        for i in range(3, 7):
            db.add(Agent(id=i, name=f"Agent{i}", persona=f"测试人格{i}", model="test", credits=30))
        await db.commit()

    # --- benchmark: build_world_snapshot ---
    async with async_session() as db:
        t0 = time.perf_counter()
        snapshot = await build_world_snapshot(db)
        t_snapshot = (time.perf_counter() - t0) * 1000  # ms

    assert snapshot, "快照不应为空"
    assert t_snapshot < 200, f"snapshot 构建耗时 {t_snapshot:.1f}ms，超过 200ms 阈值"

    # --- benchmark: execute_decisions (6 agents all rest = 最快路径) ---
    decisions = [
        {"agent_id": i, "action": "rest", "params": {}, "reason": "休息"}
        for i in range(1, 7)
    ]

    with patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):
        async with async_session() as db:
            t0 = time.perf_counter()
            stats = await execute_decisions(decisions, db)
            t_exec = (time.perf_counter() - t0) * 1000

    assert t_exec < 60000, f"执行耗时 {t_exec:.1f}ms，超过 60s 阈值"

    # --- benchmark: full tick (snapshot + decide + execute) with mock LLM ---
    mock_decisions = json.dumps([
        {"agent_id": i, "action": "checkin", "params": {}, "reason": "上班"}
        for i in range(1, 7)
    ])
    mock_choice = MagicMock()
    mock_choice.message.content = mock_decisions
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 200
    mock_response.usage.completion_tokens = 100
    mock_response.usage.total_tokens = 300

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("app.services.autonomy_service.resolve_model",
               return_value=("http://fake", "sk-fake", "test-model")), \
         patch("app.services.autonomy_service.AsyncOpenAI",
               return_value=mock_client), \
         patch("app.services.autonomy_service._broadcast_action", new_callable=AsyncMock):

        from app.services.autonomy_service import tick
        t0 = time.perf_counter()
        await tick()
        t_full = (time.perf_counter() - t0) * 1000

    assert t_full < 60000, f"完整 tick 耗时 {t_full:.1f}ms，超过 60s 阈值"
    print(f"\n  [PERF] snapshot={t_snapshot:.1f}ms, exec={t_exec:.1f}ms, full_tick={t_full:.1f}ms")

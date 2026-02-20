# SR-P3：悬赏 Agent 自主接取

> 状态：待评审
> 对应 IR：IR-M6.2 P3
> 目标：让 Agent 在自主决策循环中浏览开放悬赏并决定是否接取

---

## 1. 概述

当前悬赏系统 CRUD + 前端 UI 已完整（M2 Phase 5），但自主决策引擎完全不知道悬赏的存在。本 SR 覆盖：

1. 新建 `bounty_service.py` — 从 API 层抽取业务逻辑，供 autonomy 和 tool_call 复用
2. `autonomy_service.py` — 世界快照 + SYSTEM_PROMPT + 白名单 + 执行分支 + 广播
3. `tool_registry.py` — 注册 `claim_bounty` 工具
4. `bounties.py` — 重构为调用 bounty_service

### 已确认决策（IR 原文）

- DC-6：M6.2 只做 claim，不做 complete_bounty 自主完成
- DC-7：不硬编码前置条件，执行层原子校验兜底，失败消耗完整 tick，SYSTEM_PROMPT 自然语言引导
- DC-8：同一 Agent 同时最多接取 1 个悬赏

---

## 2. bounty_service.py（新建）

路径：`server/app/services/bounty_service.py`

### 2.1 事务策略

**不自行 commit / rollback**。只做 `db.flush()` 刷新状态，由调用方（API endpoint 或 autonomy tick 的统一 commit）控制事务边界。

### 2.2 接口定义

```python
async def claim_bounty(
    agent_id: int,
    bounty_id: int,
    *,
    db: AsyncSession,
) -> dict:
    """
    接取悬赏。原子校验 + 状态变更，不自行 commit。

    返回值：
        成功：{"ok": True, "bounty_id": int, "title": str, "reward": int}
        失败：{"ok": False, "reason": str}
    """
```

### 2.3 原子校验逻辑（顺序执行，任一失败立即返回）

```
1. 查询 Bounty（SELECT ... WHERE id = bounty_id）
   → 不存在 → {"ok": False, "reason": "悬赏不存在"}

2. 查询 Agent（SELECT ... WHERE id = agent_id）
   → 不存在 → {"ok": False, "reason": "居民不存在"}

3. 检查该 Agent 是否已有进行中悬赏
   SELECT count(*) FROM bounties
   WHERE claimed_by = agent_id AND status = 'claimed'
   → count > 0 → {"ok": False, "reason": "你已有进行中的悬赏，完成后才能接取新的"}

4. 原子 CAS 更新（先到先得）
   UPDATE bounties
   SET status = 'claimed', claimed_by = agent_id
   WHERE id = bounty_id AND status = 'open'
   → rowcount == 0 → {"ok": False, "reason": "该悬赏已被接取或不再开放"}

5. await db.flush()

6. return {"ok": True, "bounty_id": bounty_id, "title": bounty.title, "reward": bounty.reward}
```

### 2.4 依赖

```python
from sqlalchemy import select, update, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from ..models.tables import Bounty, Agent
```

不引入任何 WebSocket / broadcast 依赖 — 广播由调用方负责。

---

## 3. autonomy_service.py 改动

### 3.1 build_world_snapshot() — 新增悬赏板块

在现有第 10 板块（交易市场）之后，新增第 11 板块。

**数据查询**（插入位置：`build_world_snapshot` 函数内，交易市场查询之后）：

```python
# 11. 悬赏任务
from ..models.tables import Bounty
bounty_result = await db.execute(
    select(Bounty).where(Bounty.status.in_(["open", "claimed"]))
)
bounties = bounty_result.scalars().all()
bounty_lines = []
for b in bounties:
    if b.status == "open":
        bounty_lines.append(
            f"- 悬赏#{b.id}: {b.title} | 奖励={b.reward}信用点 | 状态=开放"
        )
    else:
        bounty_lines.append(
            f"- 悬赏#{b.id}: {b.title} | 奖励={b.reward}信用点 | "
            f"状态=进行中(接取者ID={b.claimed_by})"
        )
bounty_lines = bounty_lines or ["(无悬赏)"]
```

**快照输出格式**（追加到 snapshot 模板，在"交易市场"之后、"请为每个居民"之前）：

```
== 悬赏任务 ==
- 悬赏#1: 收集100小麦 | 奖励=50信用点 | 状态=开放
- 悬赏#2: 建造磨坊 | 奖励=80信用点 | 状态=进行中(接取者ID=3)
```

### 3.2 SYSTEM_PROMPT 改动

**行为列表**末尾追加 `claim_bounty`（修改 SYSTEM_PROMPT 字符串常量）：

```
行为：checkin（打卡）、purchase（购买）、chat（聊天）、rest（休息）、
assign_building（应聘建筑）、unassign_building（离职）、eat（吃饭）、
transfer_resource（转赠资源）、create_market_order（挂单交易）、
accept_market_order（接单交易）、cancel_market_order（撤单）、
construct_building（建造建筑）、claim_bounty（接取悬赏）
```

**规则列表**末尾追加第 10 条：

```
10. claim_bounty：浏览悬赏任务板，选择感兴趣且有能力完成的悬赏接取。
    你同时只能接取一个悬赏，接取前考虑自身能力和竞争概率。
    已有进行中悬赏时不要再接新的
```

**params 格式**末尾追加：

```
claim_bounty={"bounty_id": <int>}
```

### 3.3 _validate_actions() 白名单

在白名单元组中追加 `"claim_bounty"`：

```python
if d["action"] not in (
    "checkin", "purchase", "chat", "rest",
    "assign_building", "unassign_building", "eat",
    "transfer_resource", "create_market_order",
    "accept_market_order", "cancel_market_order",
    "construct_building", "claim_bounty",
):
```

### 3.4 execute_decisions() 新增 elif 分支

在 `construct_building` 分支之后、`round_log.append` 之前，新增：

```python
elif action == "claim_bounty":
    bounty_id = params.get("bounty_id")
    if bounty_id:
        from .bounty_service import claim_bounty
        res = await claim_bounty(
            agent_id=aid, bounty_id=bounty_id, db=db,
        )
        if res["ok"]:
            stats["success"] += 1
            await _broadcast_action(
                agent_name, aid, "claim_bounty", reason,
            )
            await _broadcast_bounty_event("bounty_claimed", {
                "bounty_id": res["bounty_id"],
                "title": res["title"],
                "reward": res["reward"],
                "claimed_by": aid,
                "claimed_by_name": agent_name,
            })
        else:
            logger.info(
                "Autonomy claim_bounty failed for %s: %s",
                agent_name, res["reason"],
            )
            stats["failed"] += 1
    else:
        stats["failed"] += 1
```

**失败处理**：与 purchase / checkin 一致 — 失败计入 `stats["failed"]`，消耗完整 tick，失败原因通过 `round_log` 写入上一轮行为板块，LLM 下轮可见。

### 3.5 新增 _broadcast_bounty_event 辅助函数

位置：`autonomy_service.py` 内，`_broadcast_action` 函数之后。

```python
async def _broadcast_bounty_event(event: str, data: dict):
    """广播悬赏相关的 WS 事件，失败不回滚状态变更"""
    from ..api.chat import broadcast
    try:
        await broadcast({
            "type": "system_event",
            "data": {
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(
                    timespec="seconds",
                ),
                **data,
            },
        })
    except Exception as e:
        logger.warning("Bounty broadcast failed (non-fatal): %s", e)
```

**关键约束**：广播失败不回滚状态变更（try/except 吞异常，只写 warning log）。满足 AC-8。

---

## 4. tool_registry.py 改动

### 4.1 新增 handler

位置：文件末尾，`CONSTRUCT_BUILDING_TOOL` 注册之后。

```python
async def _handle_claim_bounty(arguments: dict, context: dict) -> dict:
    """claim_bounty handler。agent_id 从 context 取。"""
    from .bounty_service import claim_bounty
    db = context["db"]
    agent_id = context["agent_id"]
    bounty_id = arguments["bounty_id"]
    result = await claim_bounty(
        agent_id=agent_id, bounty_id=bounty_id, db=db,
    )
    if result["ok"]:
        await db.commit()
    return result
```

注意：tool_call 场景下由 handler 自行 commit（与现有 transfer_resource 等工具行为一致）。

### 4.2 新增 ToolDefinition + 注册

```python
CLAIM_BOUNTY_TOOL = ToolDefinition(
    name="claim_bounty",
    description="接取悬赏任务，同时只能接取一个",
    parameters={
        "type": "object",
        "properties": {
            "bounty_id": {
                "type": "integer",
                "description": "要接取的悬赏任务 ID",
            },
        },
        "required": ["bounty_id"],
    },
    handler=_handle_claim_bounty,
)

tool_registry.register(CLAIM_BOUNTY_TOOL)
```

---

## 5. bounties.py API 层重构

### 5.1 claim_bounty endpoint 重构

将现有 `claim_bounty` endpoint 的内联业务逻辑替换为调用 `bounty_service`：

```python
@router.post("/{bounty_id}/claim", response_model=BountyOut)
async def claim_bounty_endpoint(
    bounty_id: int,
    agent_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    from ..services.bounty_service import claim_bounty
    result = await claim_bounty(
        agent_id=agent_id, bounty_id=bounty_id, db=db,
    )
    if not result["ok"]:
        reason = result["reason"]
        if "不存在" in reason:
            raise HTTPException(404, reason)
        else:
            raise HTTPException(409, reason)
    await db.commit()
    bounty = await db.get(Bounty, bounty_id)
    return bounty
```

### 5.2 不改动的 endpoint

- `create_bounty` — 保持原样（逻辑简单，无需抽取）
- `list_bounties` — 保持原样
- `complete_bounty` — 保持原样（M6.2 不做自主 complete）

### 5.3 可清理的 import

重构后 `claim_bounty_endpoint` 不再直接使用 `update`，但 `complete_bounty` 仍需要，故 `update` import 保留。`Agent` import 可移除（bounty_service 内部校验 agent 存在性），但保留亦无害。

---

## 6. WebSocket 事件 payload 定义

### 6.1 bounty_claimed 事件

触发时机：`claim_bounty` 执行成功后，由 `autonomy_service._broadcast_bounty_event` 发出。

```json
{
    "type": "system_event",
    "data": {
        "event": "bounty_claimed",
        "bounty_id": 1,
        "title": "收集100小麦",
        "reward": 50,
        "claimed_by": 3,
        "claimed_by_name": "Alice",
        "timestamp": "2026-02-20T12:00:00+00:00"
    }
}
```

### 6.2 agent_action 事件（复用已有）

`_broadcast_action` 照常发出 `agent_action` 事件，`action` 字段值为 `"claim_bounty"`：

```json
{
    "type": "system_event",
    "data": {
        "event": "agent_action",
        "agent_id": 3,
        "agent_name": "Alice",
        "action": "claim_bounty",
        "reason": "这个悬赏奖励丰厚，我有能力完成",
        "timestamp": "2026-02-20T12:00:00+00:00"
    }
}
```

### 6.3 广播解耦保证

`_broadcast_bounty_event` 内部 try/except 吞异常 → 广播失败不影响悬赏状态变更（AC-8）。

---

## 7. 事务边界说明

| 调用场景 | commit 位置 | 说明 |
|----------|-------------|------|
| API endpoint (`bounties.py`) | endpoint 内 `await db.commit()` | bounty_service 只 flush，endpoint commit |
| autonomy tick (`execute_decisions`) | 函数末尾统一 `await db.commit()` | 所有 action 共享同一事务 |
| tool_call (`tool_registry.py`) | handler 内 `await db.commit()` | 与 transfer_resource 等工具一致 |

**bounty_service 内部只做 `await db.flush()`**，确保 ORM 对象状态刷新但不提交。调用方负责 commit 或 rollback。


---

## 8. 错误处理

| 错误场景 | bounty_service 返回 | API 层映射 | autonomy 层处理 |
|----------|---------------------|------------|-----------------|
| 悬赏不存在 | `{"ok": False, "reason": "悬赏不存在"}` | HTTP 404 | `stats["failed"] += 1` |
| 居民不存在 | `{"ok": False, "reason": "居民不存在"}` | HTTP 404 | `stats["failed"] += 1` |
| 已有进行中悬赏 | `{"ok": False, "reason": "你已有进行中的悬赏，完成后才能接取新的"}` | HTTP 409 | `stats["failed"] += 1` |
| 悬赏已被接取/不再开放 | `{"ok": False, "reason": "该悬赏已被接取或不再开放"}` | HTTP 409 | `stats["failed"] += 1` |
| 参数缺失（bounty_id） | 不进入 service | FastAPI 422 | `stats["failed"] += 1`（params 缺失分支） |

autonomy 层所有失败均消耗完整 tick，失败原因写入 `round_log`，LLM 下轮可见。

---

## 9. 改动文件清单（函数级）

| 文件 | 函数/位置 | 改动类型 | 说明 |
|------|-----------|----------|------|
| `server/app/services/bounty_service.py` | `claim_bounty()` | 新建文件 | 业务逻辑，不自行 commit |
| `server/app/services/autonomy_service.py` | `build_world_snapshot()` | 修改 | 新增悬赏板块（第 11 板块） |
| `server/app/services/autonomy_service.py` | `SYSTEM_PROMPT` | 修改 | 行为列表 + 规则 + params 格式 |
| `server/app/services/autonomy_service.py` | `_validate_actions()` | 修改 | 白名单追加 `claim_bounty` |
| `server/app/services/autonomy_service.py` | `execute_decisions()` | 修改 | 新增 `claim_bounty` elif 分支 |
| `server/app/services/autonomy_service.py` | `_broadcast_bounty_event()` | 新增函数 | 悬赏专用广播，失败不回滚 |
| `server/app/services/tool_registry.py` | `_handle_claim_bounty()` | 新增函数 | tool_call handler |
| `server/app/services/tool_registry.py` | `CLAIM_BOUNTY_TOOL` | 新增常量 | ToolDefinition + 注册 |
| `server/app/api/bounties.py` | `claim_bounty_endpoint()` | 修改 | 重构为调用 bounty_service |

### 不改动的文件

| 文件 | 原因 |
|------|------|
| `server/app/models/tables.py` | Bounty 表结构已满足（status: open/claimed/completed, claimed_by） |
| `server/app/api/schemas.py` | BountyCreate / BountyOut 已满足 |
| `bounties.py` 的 `create_bounty` / `list_bounties` / `complete_bounty` | 无需改动 |
| 前端文件 | P3 不涉及前端，WS 事件由现有 system_event 处理器自动展示 |

---

## 10. 测试用例

### 10.1 单元测试 — `tests/test_bounty_service.py`

```python
import pytest

@pytest.mark.asyncio
async def test_claim_bounty_success(db_session, seed_agent, seed_bounty):
    """开放悬赏 + 无进行中悬赏 → claim 成功"""
    # 断言：result["ok"] is True
    # 断言：result["bounty_id"] == seed_bounty.id
    # 断言：result["title"] == seed_bounty.title
    # 断言：result["reward"] == seed_bounty.reward

@pytest.mark.asyncio
async def test_claim_bounty_not_found(db_session, seed_agent):
    """bounty_id 不存在 → ok=False, reason 含"悬赏不存在" """
    # 断言：result["ok"] is False
    # 断言："悬赏不存在" in result["reason"]

@pytest.mark.asyncio
async def test_claim_bounty_agent_not_found(db_session, seed_bounty):
    """agent_id 不存在 → ok=False, reason 含"居民不存在" """
    # 断言：result["ok"] is False
    # 断言："居民不存在" in result["reason"]

@pytest.mark.asyncio
async def test_claim_bounty_already_has_active(db_session, seed_agent, seed_two_bounties):
    """Agent 已有 claimed 悬赏 → 拒绝"""
    # 前置：seed_two_bounties[0] 已被 seed_agent claim
    # 操作：claim seed_two_bounties[1]
    # 断言：result["ok"] is False
    # 断言："已有进行中" in result["reason"]

@pytest.mark.asyncio
async def test_claim_bounty_already_claimed_by_other(db_session, seed_agent, seed_claimed_bounty):
    """悬赏已被其他 Agent 接取 → CAS 失败"""
    # 前置：seed_claimed_bounty.status = "claimed", claimed_by = other_agent
    # 断言：result["ok"] is False
    # 断言："已被接取" in result["reason"]

@pytest.mark.asyncio
async def test_claim_bounty_completed_bounty(db_session, seed_agent, seed_completed_bounty):
    """悬赏已完成 → CAS 失败"""
    # 前置：seed_completed_bounty.status = "completed"
    # 断言：result["ok"] is False

@pytest.mark.asyncio
async def test_claim_bounty_no_self_commit(db_session, seed_agent, seed_bounty):
    """验证 claim_bounty 不调用 db.commit()，只调用 db.flush()"""
    # 用 mock 包装 db.commit 和 db.flush
    # 断言：db.commit 未被调用
    # 断言：db.flush 被调用至少 1 次
```

### 10.2 单元测试 — `tests/test_autonomy_bounty.py`

```python
import pytest
from server.app.services.autonomy_service import (
    build_world_snapshot, _validate_actions,
)

@pytest.mark.asyncio
async def test_world_snapshot_contains_bounties(db_session, seed_agent, seed_bounty):
    """build_world_snapshot 返回的快照包含"悬赏任务"板块"""
    # 前置：DB 中有 1 个 open 悬赏
    # 断言："== 悬赏任务 ==" in snapshot
    # 断言："状态=开放" in snapshot

@pytest.mark.asyncio
async def test_world_snapshot_shows_claimed_bounty(db_session, seed_agent, seed_claimed_bounty):
    """快照中 claimed 悬赏显示接取者 ID"""
    # 断言："状态=进行中" in snapshot
    # 断言：f"接取者ID={seed_agent.id}" in snapshot

def test_validate_actions_allows_claim_bounty():
    """_validate_actions 不过滤 claim_bounty"""
    raw = [{"agent_id": 1, "action": "claim_bounty", "params": {"bounty_id": 1}}]
    result = _validate_actions(raw)
    # 断言：len(result) == 1
    # 断言：result[0]["action"] == "claim_bounty"

def test_validate_actions_rejects_unknown():
    """未知行为降级为 rest"""
    raw = [{"agent_id": 1, "action": "fly_to_moon", "params": {}}]
    result = _validate_actions(raw)
    # 断言：result[0]["action"] == "rest"

@pytest.mark.asyncio
async def test_execute_claim_bounty_success(db_session, seed_agent, seed_bounty, mocker):
    """execute_decisions 中 claim_bounty 成功 → stats.success + 双广播"""
    # mock _broadcast_action 和 _broadcast_bounty_event
    # 输入：[{"agent_id": seed_agent.id, "action": "claim_bounty",
    #         "params": {"bounty_id": seed_bounty.id}, "reason": "测试"}]
    # 断言：stats["success"] >= 1
    # 断言：_broadcast_action 被调用，action="claim_bounty"
    # 断言：_broadcast_bounty_event 被调用，event="bounty_claimed"

@pytest.mark.asyncio
async def test_execute_claim_bounty_failure_consumes_tick(db_session, seed_agent, mocker):
    """claim_bounty 失败 → stats.failed，不广播 bounty_claimed"""
    # mock bounty_service.claim_bounty 返回 ok=False
    # 断言：stats["failed"] >= 1
    # 断言：_broadcast_bounty_event 未被调用

@pytest.mark.asyncio
async def test_execute_claim_bounty_missing_params(db_session, seed_agent):
    """params 中无 bounty_id → stats.failed"""
    # 输入：{"agent_id": 1, "action": "claim_bounty", "params": {}}
    # 断言：stats["failed"] >= 1
```

### 10.3 单元测试 — `tests/test_tool_claim_bounty.py`

```python
import pytest
from server.app.services.tool_registry import tool_registry

def test_tool_registry_has_claim_bounty():
    """tool_registry 包含 claim_bounty 工具"""
    tools = tool_registry.get_tools_for_llm()
    names = [t["function"]["name"] for t in tools]
    # 断言："claim_bounty" in names

def test_claim_bounty_tool_schema():
    """claim_bounty 工具 schema 包含 bounty_id 必填参数"""
    tools = tool_registry.get_tools_for_llm()
    claim_tool = [t for t in tools if t["function"]["name"] == "claim_bounty"][0]
    params = claim_tool["function"]["parameters"]
    # 断言："bounty_id" in params["properties"]
    # 断言："bounty_id" in params["required"]

@pytest.mark.asyncio
async def test_tool_claim_bounty_execute(db_session, seed_agent, seed_bounty):
    """通过 tool_registry.execute 调用 claim_bounty"""
    context = {"db": db_session, "agent_id": seed_agent.id}
    result = await tool_registry.execute(
        "claim_bounty", {"bounty_id": seed_bounty.id}, context,
    )
    # 断言：result["ok"] is True
    # 断言：result["result"]["bounty_id"] == seed_bounty.id
```

### 10.4 系统测试（ST）— `tests/test_st_bounty_claim.py`

```python
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_st_bounty_claim_full_flow(client: AsyncClient, db_session, seed_agent):
    """
    端到端：创建悬赏 → Agent 自主 claim → 验证状态 + WS 事件
    1. POST /api/bounties/ 创建悬赏 → 201
    2. 构建世界快照，确认包含悬赏
    3. 调用 execute_decisions 传入 claim_bounty action
    4. 验证 bounty.status == "claimed"
    5. 验证 bounty.claimed_by == seed_agent.id
    """

@pytest.mark.asyncio
async def test_st_bounty_claim_concurrent(db_session, seed_two_agents, seed_bounty):
    """
    并发竞争：2 个 Agent 同时 claim 同一悬赏 → 只有 1 个成功
    1. 创建 1 个 open 悬赏
    2. asyncio.gather 并发调用 claim_bounty(agent_1) 和 claim_bounty(agent_2)
    3. 断言：恰好 1 个 ok=True，1 个 ok=False
    4. 断言：bounty.claimed_by 是成功的那个 agent
    """

@pytest.mark.asyncio
async def test_st_bounty_api_regression(client: AsyncClient, db_session, seed_agent):
    """
    回归：原有 CRUD API 行为不变
    1. POST /api/bounties/ → 201
    2. GET /api/bounties/ → 包含新建悬赏
    3. POST /api/bounties/{id}/claim?agent_id=X → 200
    4. POST /api/bounties/{id}/complete?agent_id=X → 200
    5. GET /api/bounties/?status=completed → 包含已完成悬赏
    """

@pytest.mark.asyncio
async def test_st_bounty_claim_limit_one(db_session, seed_agent):
    """
    同时接取上限 1：Agent 已有 claimed 悬赏 → 再 claim 被拒
    1. 创建 2 个 open 悬赏
    2. Agent claim 第 1 个 → 成功
    3. Agent claim 第 2 个 → 失败，reason 含"已有进行中"
    """
```

---

## 11. 参考文件

| 文件 | 用途 |
|------|------|
| `server/app/services/market_service.py` | service 层模式参考（函数签名、返回值格式） |
| `server/app/services/city_service.py` | execute_decisions 中的调用模式参考 |
| `server/app/services/tool_registry.py` | 工具注册模式参考 |
| `server/app/api/bounties.py` | 现有 API 实现，重构基础 |
| `server/app/models/tables.py` | Bounty 表结构确认 |
| `docs/specs/SPEC-001-核心系统/M6.2-原型对齐/IR-M6.2-原型对齐补丁包.md` | IR 原文 |

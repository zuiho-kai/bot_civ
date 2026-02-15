# TDD-M2: 记忆系统与经济系统 技术设计

> M2 里程碑技术设计文档。基于 02-需求拆分.md 中的任务分解，定义具体实现方案。

---

## 1. 架构总览

```
                    Frontend (React + Vite)
  +----------+  +--------------+  +------------------------+
  | ChatRoom |  | EconomyPanel |  | BountyPage             |
  +----+-----+  +------+-------+  +--------+---------------+
       +---------------+-------------------+
                       | WebSocket + REST
                  Server (FastAPI)
  +--------------------v----------------------------+
  |           WebSocket Hub (chat.py)                |
  |    + economy_check hook + memory_extract hook    |
  +------+---------------+---------------+----------+
  +------v------+ +------v------+ +------v-----------------+
  | WakeupSvc   | | EconomySvc  | | MemoryService          |
  +------+------+ +-------------+ +------+-----------------+
  +------v-------------------------------v-----------------+
  |           AgentRunner (agent_runner.py)                  |
  |        + memory injection in system prompt               |
  +------+-------------------------------+-----------------+
  +------v-----------+          +--------v----------------+
  |  SQLite (ORM)    |          |  LanceDB (向量存储)      |
  +------------------+          +--------------------------+
```

### 新增模块清单

| 文件 | 职责 | 任务 ID |
|------|------|---------|
| `app/services/vector_store.py` | LanceDB 初始化 + 向量嵌入 | M2-1 |
| `app/services/memory_service.py` | 记忆 CRUD + 语义搜索 + 过期清理 | M2-2 |
| `app/services/economy_service.py` | 额度检查 + 信用点扣减 + 转账 | M2-5 |
| `app/services/scheduler.py` | 每日发放 + 记忆清理定时任务 | M2-7 |
| `app/api/bounties.py` | 悬赏任务 REST API | M2-8 |

### 修改模块清单

| 文件 | 修改内容 | 任务 ID |
|------|----------|---------|
| `app/services/agent_runner.py` | system prompt 注入记忆 + batch_generate() | M2-3, M2-12 |
| `app/api/chat.py` | 唤醒前经济预检查 + 回复后记忆提取 | M2-4, M2-6 |
| `app/services/wakeup_service.py` | 定时触发路径改用 batch 调用 + 错开广播 | M2-12 |
| `app/main.py` | lifespan 注册定时任务 + LanceDB 初始化 | M2-1, M2-7 |

---

## 2. 记忆系统

### 2.1 向量存储层 (M2-1)

**文件**: `app/services/vector_store.py`

Embedding 模型选型:
- 模型: `BAAI/bge-small-zh-v1.5` (中英双语, ~95MB, 512维)
- 理由: 中文效果远优于 all-MiniLM-L6-v2, 体积可控, HuggingFace 开源
- 加载: 首次启动时下载到 `data/models/`, 后续本地加载

```python
# vector_store.py 伪代码

import lancedb
from sentence_transformers import SentenceTransformer

_db: lancedb.DBConnection = None
_model: SentenceTransformer = None
TABLE_NAME = "memories"

async def init_vector_store(lancedb_path: str):
    """lifespan 启动时调用"""
    global _db, _model
    _db = lancedb.connect(lancedb_path)
    _model = SentenceTransformer("BAAI/bge-small-zh-v1.5")
    if TABLE_NAME not in _db.table_names():
        _db.create_table(TABLE_NAME, schema={
            "memory_id": "int",
            "agent_id": "int",       # -1 = 公共记忆
            "text": "str",
            "memory_type": "str",     # short/long/public
            "vector": "vector[512]",
            "created_at": "str",
        })

def embed(text: str) -> list[float]:
    return _model.encode(text).tolist()

def upsert_memory(memory_id, agent_id, text, memory_type):
    table = _db.open_table(TABLE_NAME)
    vector = embed(text)
    table.add([{
        "memory_id": memory_id,
        "agent_id": agent_id,
        "text": text,
        "memory_type": memory_type,
        "vector": vector,
        "created_at": datetime.now().isoformat(),
    }])

def search_memories(query: str, agent_id: int, top_k: int = 5):
    """搜索该 agent 的个人记忆 + 公共记忆"""
    table = _db.open_table(TABLE_NAME)
    q_vec = embed(query)
    results = (table.search(q_vec)
               .where(f"agent_id = {agent_id} OR agent_id = -1")
               .limit(top_k)
               .to_list())
    return results

def delete_memory(memory_id: int):
    table = _db.open_table(TABLE_NAME)
    table.delete(f"memory_id = {memory_id}")
```

### 2.1.1 设计备注：向量检索 vs LLM 检索

> **讨论日期**: 2026-02-15
> **参考**: MaiBot 竞品分析 (`docs/runbooks/reference-maibot-analysis.md` §3.2)

MaiBot 不使用向量数据库，记忆检索完全靠 LLM ReAct Agent 多轮推理（关键词 SQL 查询 + LLM 语义理解）。对比：

| | 我们（LanceDB + sentence-transformers） | MaiBot（纯 LLM ReAct） |
|---|---|---|
| embedding | 本地 bge-small-zh-v1.5，免费 | 不需要 |
| 每次检索成本 | 0（本地向量计算） | 1-5 次 LLM 调用 |
| 检索质量 | 中（向量近似匹配） | 高（LLM 理解语义 + 多轮推理） |
| 适合场景 | 高频批量（定时唤醒 5-20 Agent） | 低频精准（单 Bot） |

**当前决策**：M2 阶段全部使用向量检索，成本可控。

**M3 混合方案预留**：对于高价值场景（@必唤、悬赏任务），可以在向量检索基础上追加一轮 LLM 精排/补充检索，提升召回质量。定时唤醒等批量场景仍用纯向量检索。此方案不影响 M2 接口设计，`MemoryService.search()` 未来可内部切换策略而不改调用方。

---

### 2.2 记忆读写服务 (M2-2)

**文件**: `app/services/memory_service.py`

```python
PROMOTE_THRESHOLD = 5   # access_count 达到此值升级为长期记忆
SHORT_MEMORY_TTL_DAYS = 7

class MemoryService:

    async def save_memory(self, agent_id, content, memory_type, db):
        """写 SQLite + LanceDB 双写"""
        expires_at = (datetime.now() + timedelta(days=SHORT_MEMORY_TTL_DAYS)
                      if memory_type == "short" else None)
        mem = Memory(
            agent_id=agent_id,
            memory_type=memory_type,
            content=content,
            expires_at=expires_at,
        )
        db.add(mem)
        await db.commit()
        await db.refresh(mem)
        lance_agent_id = agent_id if agent_id is not None else -1
        upsert_memory(mem.id, lance_agent_id, content, memory_type)
        return mem

    async def search(self, agent_id, query, top_k=5, db=None):
        """语义搜索, 返回相关记忆, 同时 access_count += 1"""
        results = search_memories(query, agent_id, top_k)
        memory_ids = [r["memory_id"] for r in results]
        if not memory_ids or not db:
            return []
        # 批量更新 access_count
        stmt = (update(Memory)
                .where(Memory.id.in_(memory_ids))
                .values(access_count=Memory.access_count + 1))
        await db.execute(stmt)
        await self._check_promote(memory_ids, db)
        await db.commit()
        result = await db.execute(
            select(Memory).where(Memory.id.in_(memory_ids)))
        return result.scalars().all()

    async def _check_promote(self, memory_ids, db):
        """access_count >= 阈值的短期记忆升级为长期"""
        stmt = (update(Memory)
                .where(Memory.id.in_(memory_ids))
                .where(Memory.memory_type == "short")
                .where(Memory.access_count >= PROMOTE_THRESHOLD)
                .values(memory_type="long", expires_at=None))
        await db.execute(stmt)

    async def cleanup_expired(self, db) -> int:
        """清理过期短期记忆 (SQLite + LanceDB)"""
        expired = await db.execute(
            select(Memory).where(
                Memory.memory_type == "short",
                Memory.expires_at < datetime.now()))
        count = 0
        for mem in expired.scalars().all():
            delete_memory(mem.id)
            await db.delete(mem)
            count += 1
        await db.commit()
        return count

memory_service = MemoryService()
```

### 2.3 记忆注入 Agent 上下文 (M2-3)

**修改**: `app/services/agent_runner.py`

在 `generate_reply()` 中, 构建 system prompt 后, 发送 LLM 请求前, 注入记忆:

```python
MAX_MEMORY_TOKENS = 500  # 记忆注入最大长度 (字符数近似)

async def generate_reply(self, chat_history, db=None):
    # ... 现有上下文构建逻辑 ...
    system_msg = SYSTEM_PROMPT_TEMPLATE.format(
        name=self.name, persona=self.persona)

    # === 新增: 记忆注入 ===
    if db:
        recent_text = " ".join([m["content"] for m in chat_history[-3:]])
        memories = await memory_service.search(
            self.agent_id, recent_text, top_k=5, db=db)
        if memories:
            personal = [m for m in memories if m.memory_type in ("short", "long")]
            public = [m for m in memories if m.memory_type == "public"]
            mem_block = ""
            if personal:
                mem_block += "\n\n## 你的相关记忆\n"
                for m in personal[:3]:
                    mem_block += f"- {m.content}\n"
            if public:
                mem_block += "\n## 公共知识\n"
                for m in public[:2]:
                    mem_block += f"- {m.content}\n"
            if len(mem_block) > MAX_MEMORY_TOKENS:
                mem_block = mem_block[:MAX_MEMORY_TOKENS] + "..."
            system_msg += mem_block

    messages = [{"role": "system", "content": system_msg}]
    # ... 后续不变 ...
```

关键变更: `generate_reply` 签名新增可选参数 `db: AsyncSession = None`, 调用方 (chat.py handle_wakeup) 传入 db session。

### 2.4 对话自动提取记忆 (M2-4)

**修改**: `app/api/chat.py`

Agent 回复成功后, 异步提取记忆:

```python
async def _extract_memory(agent_id, recent_messages):
    """每 5 轮对话自动摘要为短期记忆"""
    if len(recent_messages) < 5:
        return
    combined = "\n".join(
        [f"{m['name']}: {m['content']}" for m in recent_messages[-5:]])
    summary = f"对话摘要: {combined[:200]}"
    async with async_session() as db:
        await memory_service.save_memory(agent_id, summary, "short", db)
```

触发条件: 每个 Agent 维护一个消息计数器, 每 5 条回复触发一次提取。

---

## 3. 经济系统

### 3.1 经济服务 (M2-5)

**文件**: `app/services/economy_service.py`

```python
from datetime import date

class CanSpeakResult:
    def __init__(self, allowed: bool, reason: str = ""):
        self.allowed = allowed
        self.reason = reason

class EconomyService:

    async def check_quota(self, agent_id, message_type, db):
        """预检查 (只读语义, 但会惰性重置额度)"""
        if agent_id == 0:
            return CanSpeakResult(True)  # Human 不受限

        agent = await db.get(Agent, agent_id)
        if not agent:
            return CanSpeakResult(False, "agent_not_found")

        if message_type == "work":
            return CanSpeakResult(True)  # 工作发言免费

        # 惰性额度重置
        today = date.today()
        if agent.quota_reset_date != today:
            agent.quota_reset_date = today
            agent.quota_used_today = 0
            await db.commit()

        if agent.quota_used_today < agent.daily_free_quota:
            return CanSpeakResult(True)

        if agent.credits >= 1:
            return CanSpeakResult(True)

        return CanSpeakResult(False, "insufficient_credits")

    async def deduct_quota(self, agent_id, db):
        """真正扣减 (写入)"""
        agent = await db.get(Agent, agent_id)
        if not agent or agent_id == 0:
            return
        if agent.quota_used_today < agent.daily_free_quota:
            agent.quota_used_today += 1
        else:
            agent.credits = max(0, agent.credits - 1)
        await db.commit()

    async def transfer_credits(self, from_id, to_id, amount, db):
        """转账, 返回是否成功"""
        if amount <= 0:
            return False
        sender = await db.get(Agent, from_id)
        receiver = await db.get(Agent, to_id)
        if not sender or not receiver or sender.credits < amount:
            return False
        sender.credits -= amount
        receiver.credits += amount
        await db.commit()
        return True

    async def get_balance(self, agent_id, db):
        agent = await db.get(Agent, agent_id)
        if not agent:
            return None
        return {
            "credits": agent.credits,
            "quota_used": agent.quota_used_today,
            "quota_remaining": max(0, agent.daily_free_quota - agent.quota_used_today),
            "daily_free_quota": agent.daily_free_quota,
        }

economy_service = EconomyService()
```

### 3.2 发言扣费集成 (M2-6)

**修改**: `app/api/chat.py` 的 `handle_wakeup()`

```python
# handle_wakeup 修改后的核心逻辑:

MAX_CHAIN_DEPTH = 3       # 链式唤醒最大深度
CHAIN_DELAY_MIN = 30      # 链式唤醒最小延迟(秒)
CHAIN_DELAY_MAX = 60      # 链式唤醒最大延迟(秒)

async def handle_wakeup(message, wake_list, db, chain_depth=0):
    # === 防线 1: 链式深度硬性限制 ===
    if chain_depth >= MAX_CHAIN_DEPTH:
        logger.info("Chain depth %d reached limit, stopping", chain_depth)
        return

    # === Agent 消息保留消息选人, 但经过三重防线 ===
    # 注意: 不再禁止 Agent 消息走消息选人
    # 防循环由 chain_depth + 经济系统 + 强化 prompt 三重防线保障

    eligible = []
    for agent_id in wake_list:
        if agent_id in bot_connections:
            continue  # Bot 在线, 自己处理

        agent = await db.get(Agent, agent_id)
        if not agent:
            continue

        # === 防线 2: 经济系统硬性限制 ===
        check = await economy_service.check_quota(agent_id, "chat", db)
        if not check.allowed:
            logger.info("Agent %d skipped: %s", agent_id, check.reason)
            continue

        eligible.append(agent)

    # === 并发调用 (同时生成多个 agent 回复) ===
    async def _generate_one(agent):
        history = await build_history(agent.id, db)
        reply = await runner_manager.runners[agent.id].generate_reply(history, db=db)
        return (agent, reply)

    results = await asyncio.gather(
        *[_generate_one(a) for a in eligible],
        return_exceptions=True)

    for result in results:
        if isinstance(result, Exception):
            logger.error("Agent generate failed: %s", result)
            continue
        agent, reply = result
        if not reply:
            continue

        # === 链式唤醒延迟 (chain_depth > 0 时生效) ===
        if chain_depth > 0:
            delay = random.uniform(CHAIN_DELAY_MIN, CHAIN_DELAY_MAX)
            await asyncio.sleep(delay)

        await send_agent_message(agent.id, agent.name, reply,
                                 chain_depth=chain_depth)
        # === 扣费 ===
        await economy_service.deduct_quota(agent.id, db)
        # === 记忆提取 ===
        asyncio.create_task(_extract_memory(agent.id, history))
```

**三重防线防循环机制**:
1. **chain_depth ≤ 3** — 硬性规则, 代码层面阻断链式唤醒
2. **经济系统** — 10 次免费 + 信用点扣费, 天然限制发言总量
3. **强化选人 Prompt** — 小模型选人时明确"发言机会珍贵, 大部分情况返回 NONE"

Agent 消息保留消息选人能力（符合三级唤醒原始设计），防循环不靠禁用机制，靠三重硬性防线。
- chain_depth 逐层 +1, 达到 MAX_CHAIN_DEPTH=3 停止
- 链式唤醒之间加 30-60s 随机延迟, 模拟思考时间
- Message 表新增 `chain_depth` 字段 (INTEGER, 默认 0)
```

### 3.3 每日发放 + 定时任务 (M2-7)

**文件**: `app/services/scheduler.py`

```python
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import update

DAILY_CREDIT_GRANT = 10

async def daily_grant():
    """每日信用点发放"""
    async with async_session() as db:
        await db.execute(
            update(Agent).values(credits=Agent.credits + DAILY_CREDIT_GRANT))
        await db.commit()

async def daily_memory_cleanup():
    """每日清理过期记忆"""
    async with async_session() as db:
        count = await memory_service.cleanup_expired(db)
    logger.info("Memory cleanup: removed %d expired memories", count)

async def scheduler_loop():
    """简单定时循环, 每日 00:00 执行"""
    while True:
        now = datetime.now()
        tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        wait_seconds = (tomorrow - now).total_seconds()
        await asyncio.sleep(wait_seconds)
        await daily_grant()
        await daily_memory_cleanup()
```

注册: 在 `app/main.py` 的 lifespan 中启动:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_vector_store(settings.lancedb_path)
    asyncio.create_task(scheduler_loop())
    yield
```

### 3.4 悬赏任务 API (M2-8)

**文件**: `app/api/bounties.py`

```python
router = APIRouter(prefix="/bounties", tags=["bounties"])

# POST /api/bounties        -- 创建悬赏
# GET  /api/bounties        -- 列表 (可按 status 筛选)
# POST /api/bounties/{id}/claim    -- 接取
# POST /api/bounties/{id}/complete -- 完成 (发放 reward 到 agent.credits)
```

Schema 新增 (`app/api/schemas.py`):

```python
class BountyCreate(BaseModel):
    title: str
    description: str = ""
    reward: int

class BountyOut(BaseModel):
    id: int
    title: str
    description: str
    reward: int
    status: str
    claimed_by: int | None
    created_at: str
    completed_at: str | None
```

---

## 4. 数据流

### 4.1 消息完整链路 (M2 增强版)

```
用户发送 -> WebSocket 接收 -> @解析 -> 持久化 -> 广播
                                                  |
                                           异步唤醒流程
                                                  |
                                      WakeupService.process()
                                                  |
                                      经济预检查 check_quota()
                                        +-- 不通过 -> 跳过
                                        +-- 通过
                                                  |
                                      记忆检索 memory_service.search()
                                                  |
                                      AgentRunner.generate_reply()
                                        (system prompt 含记忆)
                                                  |
                                      发送回复 + 经济扣费 deduct_quota()
                                                  |
                                      异步记忆提取 _extract_memory()
```

### 4.2 记忆生命周期

```
对话产生 -> 自动提取(短期, TTL=7d) -> 被检索时 access_count++
                                          |
                                   access_count >= 5
                                          |
                                   升级为长期记忆(永久)

短期记忆 -> 7天未被检索 -> 过期清理(每日 00:00)
```

---

## 5. REST API 新增

| 方法 | 路径 | 说明 | 任务 |
|------|------|------|------|
| GET | `/api/agents/{id}/balance` | 查询余额和额度 | M2-5 |
| POST | `/api/agents/{id}/transfer` | 信用点转账 | M2-5 |
| GET | `/api/agents/{id}/memories` | 查询 Agent 记忆 | M2-2 |
| POST | `/api/bounties` | 创建悬赏 | M2-8 |
| GET | `/api/bounties` | 悬赏列表 | M2-8 |
| POST | `/api/bounties/{id}/claim` | 接取悬赏 | M2-8 |
| POST | `/api/bounties/{id}/complete` | 完成悬赏 | M2-8 |

---

## 6. 前端变更

### 6.1 经济信息展示 (M2-9)

- Info Panel 新增 "经济" 标签页
- 显示当前选中 Agent 的 credits, 今日剩余额度
- Agent 侧栏卡片增加 credits 小标签
- 转账对话框: 选择目标 Agent + 输入金额
- 额度不足 toast 提示

### 6.2 悬赏任务页面 (M2-10)

- Info Panel 新增 "悬赏" 标签页
- 悬赏列表 (open/claimed/completed 筛选标签)
- 创建悬赏表单 (仅 Human 可创建)
- 接取/完成操作按钮

---

## 7. 测试计划

### 单元测试

| 测试 | 覆盖 |
|------|------|
| test_economy_check_quota | 免费额度内放行, 额度用完扣信用点, 信用点为0拒绝, 工作发言免费 |
| test_economy_transfer | 正常转账, 余额不足, 无效 agent |
| test_memory_save_search | 保存记忆 -> 语义搜索命中 |
| test_memory_promote | access_count 达标 -> short 升级为 long |
| test_memory_expire | 过期记忆被清理 |
| test_bounty_lifecycle | open -> claimed -> completed, credits 发放 |

### 端到端测试 (M2-11)

| 场景 | 验证 |
|------|------|
| Agent 聊天 -> 记忆提取 -> 后续引用 | 记忆注入 system prompt |
| 闲聊 10 次 -> 第 11 次扣信用点 | 经济扣费正确 |
| 信用点为 0 -> 拒绝发言 | 经济限制生效 |
| 创建悬赏 -> 接取 -> 完成 | credits 到账 |
| 短期记忆高频访问 -> 升级长期 | promote 逻辑 |
| Agent 转账 | 双方余额正确 |

---

## 8. 推理层 Batch 优化 (M2-12)

> 讨论详情: [Batch推理优化讨论记录](讨论细节/Batch推理优化.md)

### 8.1 背景

定时唤醒场景下，多个 Agent 同时需要生成回复。逐个调用 LLM 开销线性增长，按模型分组 batch 调用可显著降低成本。

### 8.2 优化后的定时唤醒流程

```
每小时定时触发
  → 意图识别 (Qwen 7B 免费, 1次调用)
      输入: 最近1小时聊天摘要 + 全部 agent 列表
      输出: wake_list
  → 对 wake_list 逐个:
      记忆检索 memory_service.search()
      构建 prompt (人设 + 记忆 + 上下文)
  → 按模型分组 batch 调用:
      dsv3 组:    [Alice(prompt), Bob(prompt)]  → 1次请求
      qwen32b 组: [Charlie(prompt)]             → 1次请求
  → 结果分发:
      逐个经济扣费 + 记忆提取
      错开 5-30s 随机延迟广播
```

### 8.3 每小时开销

| 步骤 | 模型 | 调用次数 | 成本 |
|---|---|---|---|
| 意图识别 | Qwen 7B (OpenRouter 免费) | 1 次 | 0 (每日 1000 次额度) |
| 思考生成 | dsv3 / qwen32b 等 | 按模型种类, 每种 1 次 | 取决于模型定价 |

示例: 5 bot (3×dsv3 + 2×qwen32b) → 每小时 1+2=3 次调用, 每日 72 次。

### 8.4 代码改造

**新增**: `AgentRunnerManager.batch_generate()`

```python
async def batch_generate(self, wake_list: list[int], chat_history, db):
    """按模型分组 batch 生成回复"""
    # 1. 逐个构建 prompt (记忆检索 + 人设)
    prompts_by_model: dict[str, list[tuple[int, list]]] = {}
    for agent_id in wake_list:
        runner = self.runners[agent_id]
        prompt = await runner.build_prompt(chat_history, db=db)
        model = runner.model
        prompts_by_model.setdefault(model, []).append((agent_id, prompt))

    # 2. 按模型分组并发调用
    results = {}
    tasks = []
    for model, agent_prompts in prompts_by_model.items():
        tasks.append(self._call_model_batch(model, agent_prompts))
    batch_results = await asyncio.gather(*tasks)
    for batch in batch_results:
        results.update(batch)

    return results  # {agent_id: reply_text}

async def _call_model_batch(self, model, agent_prompts):
    """单个模型的 batch 调用 (并发发送, 或 vLLM batch API)"""
    tasks = []
    for agent_id, prompt in agent_prompts:
        tasks.append(self._call_single(model, agent_id, prompt))
    results = await asyncio.gather(*tasks)
    return dict(results)
```

**修改**: `WakeupService` 定时触发路径

```python
# 定时触发 → 走 batch
if trigger_type == "scheduled":
    results = await runner_manager.batch_generate(wake_list, history, db)
    for agent_id, reply in results.items():
        delay = random.uniform(5, 30)  # 错开广播
        asyncio.create_task(_delayed_send(agent_id, reply, delay, db))

# @必唤 / 消息触发 → 仍走逐个调用 (实时性要求高)
else:
    for agent_id in wake_list:
        reply = await runner_manager.runners[agent_id].generate_reply(...)
        await send_agent_message(...)
```

### 8.5 适用范围

| 触发方式 | 是否 batch | 原因 |
|---|---|---|
| @必唤 | 否 | 实时性要求高, 用户期望立即回复 |
| 消息触发 (小模型选人) | 否 | 通常只选 1 个 agent, 无需 batch |
| 定时触发 (每小时) | 是 | 多 agent 同时唤醒, batch 收益最大 |

### 8.6 不影响的模块

- 记忆系统: 检索仍逐个, 只是检索完后拼进各自 prompt
- 经济系统: 扣费仍逐个
- 前端: 完全透明, 错开广播后体验不变

---

## 9. 风险与应对

| 风险 | 应对 |
|------|------|
| sentence-transformers 首次加载慢 (~30s) | lifespan 预加载, 启动时一次性开销 |
| LanceDB 与 SQLite 双写一致性 | 以 SQLite 为主, LanceDB 为辅; 不一致时重建向量 |
| embedding 模型下载失败 | 预下载到 data/models/, 离线加载 |
| 记忆注入过长挤占上下文 | MAX_MEMORY_TOKENS=500 硬截断 |
| 经济系统并发扣费竞态 | SQLite WAL + 单进程, 暂无问题; 多进程时加行锁 |
| batch 调用部分失败 | gather 用 return_exceptions=True, 失败的 agent 跳过本轮 |
| 错开广播导致消息乱序 | 广播时附带原始时间戳, 前端按时间戳排序 |

---

## 10. 实施顺序

```
Phase 1 (基础设施):
  M2-1 LanceDB 初始化 --+
  M2-5 经济服务 ---------+  可并行

Phase 2 (核心功能):
  M2-2 记忆读写 <-- M2-1
  M2-6 发言扣费 <-- M2-5    可并行
  M2-7 每日发放 <-- M2-5

Phase 3 (集成):
  M2-3 记忆注入 <-- M2-2
  M2-4 记忆提取 <-- M2-2    可并行
  M2-8 悬赏 API <-- M2-5

Phase 4 (推理优化):
  M2-12 Batch 推理 <-- M2-3, M2-6
    - AgentRunnerManager.batch_generate()
    - WakeupService 定时触发路径改造
    - 广播随机延迟 (5-30s)

Phase 5 (前端):
  M2-9 经济展示 <-- M2-5
  M2-10 悬赏页面 <-- M2-8

Phase 6 (验证):
  M2-11 端到端 <-- all
```

预计改动量: 后端 ~700-900 行新代码, 前端 ~400-600 行新代码。

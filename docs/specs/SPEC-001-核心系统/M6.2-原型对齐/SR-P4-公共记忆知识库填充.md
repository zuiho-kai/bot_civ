# SR-P4：公共记忆知识库填充

> 状态：待开发
> 对应 IR：IR-M6.2 P4
> 已确认决策：DC-9（纯世界观/规则类）、DC-10（10~15 条起步）

---

## 1. 功能目标

在服务启动时（lifespan）自动填充公共记忆种子数据，让 Agent 对话时能通过向量检索引用共享的世界观/规则知识。

---

## 2. 数据结构

### 2.1 种子数据 JSON 格式

文件路径：`server/data/public_memories.json`

```json
[
  {
    "content": "记忆内容文本"
  }
]
```

- 数组，每个元素一个 `content` 字段（字符串，非空）
- 不含 id / embedding / agent_id 等运行时字段，纯内容定义
- 编码：UTF-8

### 2.2 写入 DB 后的 Memory 行

| 字段 | 值 |
|------|-----|
| `agent_id` | `NULL`（公共记忆标识） |
| `memory_type` | `"public"` |
| `content` | JSON 中的 `content` 值 |
| `embedding` | 由 `vector_store.embed()` 生成的 float32 blob |
| `access_count` | `0` |
| `expires_at` | `NULL`（公共记忆不过期） |

---

## 3. 接口设计

### 3.1 `seed_public_memories()`

```python
# server/app/services/seed_data.py（新建文件）

async def seed_public_memories() -> None:
    """
    幂等填充公共记忆种子数据。

    逻辑：
    1. 查询 DB 中 memory_type='public' 的记录数
    2. 若 count > 0 → 跳过，打印 info log 并返回
    3. 若 count == 0 → 读取 JSON 文件，逐条插入
    4. 单条 embedding 失败 → warning log + 跳过该条，继续下一条
    5. 全部完成后打印 info log（成功 N 条 / 跳过 M 条）
    """
```

函数签名：

```python
async def seed_public_memories() -> None
```

无参数，无返回值。内部自行创建 DB session（与 `main.py` 中现有 `seed_jobs_and_items()` 模式一致，使用 `async_session()` 上下文管理器）。

### 3.2 内部流程伪代码

```
1. async with async_session() as db:
2.   count = SELECT COUNT(*) FROM memories WHERE memory_type = 'public'
3.   if count > 0:
4.     logger.info("公共记忆已存在 (%d 条)，跳过种子填充", count)
5.     return
6.
7.   seeds = _load_seed_file()  # 读取 JSON
8.   success = 0
9.   skipped = 0
10.  for item in seeds:
11.    content = item["content"].strip()
12.    if not content:
13.      skipped += 1; continue
14.    memory = Memory(agent_id=None, memory_type=MemoryType.PUBLIC, content=content)
15.    db.add(memory)
16.    await db.flush()  # 获取 memory.id，但不 commit
17.    try:
18.      await vector_store.upsert_memory(memory.id, -1, content, db)
19.      success += 1
20.    except Exception as e:
21.      logger.warning("公共记忆 embedding 失败，跳过: content=%s, error=%s", content[:50], e)
22.      await db.expunge(memory)  # 从 session 移除失败的行
23.      skipped += 1
24.
25.  await db.commit()
26.  logger.info("公共记忆种子填充完成: 成功=%d, 跳过=%d", success, skipped)
```

关键设计决策：

- **幂等判断粒度**：按 `memory_type='public'` 的总记录数判断，count > 0 即跳过全部。不做逐条 content 去重 — 种子数据是一次性批量填充，不存在"部分填充"的正常场景（中途失败的条目已被跳过，下次启动时 count > 0 仍会跳过，这是可接受的行为）
- **事务策略**：整批一次 commit（非逐条 commit），减少 IO。单条 embedding 失败时 expunge 该 Memory 对象，不影响其他条目
- **vector_store.upsert_memory 调用**：`agent_id=-1` 表示公共记忆（与 `memory_service.save_memory()` 中 `vec_agent_id = -1 if memory_type == MemoryType.PUBLIC` 一致）
- **不复用 `memory_service.save_memory()`**：因为 `save_memory()` 每条都 commit + 失败时 delete 回滚，不适合批量场景。seed 函数需要批量 flush + 单次 commit 的模式

### 3.3 `_load_seed_file()`

```python
def _load_seed_file() -> list[dict]:
    """
    读取 public_memories.json，返回种子数据列表。
    文件不存在或 JSON 解析失败 → 返回空列表 + warning log。
    """
```

- 文件路径：`Path(__file__).parent.parent.parent / "data" / "public_memories.json"`（即 `server/data/public_memories.json`）
- 返回 `list[dict]`，每个 dict 至少含 `content` 键
- 文件不存在 → `logger.warning` + 返回 `[]`
- JSON 解析失败 → `logger.warning` + 返回 `[]`
- 不阻塞服务启动

---

## 4. 种子数据内容（5 条示例 + 说明）

以下为 5 条示例，完整版 JSON 文件需包含 10~15 条。内容限定为 OpenClaw 世界观/规则类：

```json
[
  {
    "content": "长安城是所有居民的家园，城内设有农田、磨坊、集市和民居等公共建筑，居民可以在这些建筑中工作和生活。"
  },
  {
    "content": "信用点是长安城的通用货币，居民通过打卡工作获得信用点，可用于购买商品、发布悬赏或在集市交易资源。"
  },
  {
    "content": "长安城的主要资源包括小麦、面粉、木材和石材。农田产出小麦，磨坊将小麦加工为面粉，资源可在集市自由交易。"
  },
  {
    "content": "悬赏系统允许居民发布任务并设置奖励，其他居民可以接取悬赏。同一时间每位居民最多接取一个悬赏任务。"
  },
  {
    "content": "每位居民拥有饱腹度、心情和体力三项状态属性，范围 0-100。状态过低会影响工作效率和日常活动。"
  }
]
```

完整 JSON 文件还应覆盖（由开发者补齐至 10~15 条）：
- 建造系统规则（居民可建造新建筑，需消耗资源和工期）
- 工作岗位说明（矿工/农夫/程序员/教师/商人，各有不同报酬和人数上限）
- 交易市场规则（挂单交易，卖出资源换取其他资源）
- 社区公约（居民之间应友善互助，禁止恶意囤积资源）
- 每日打卡机制（每日可打卡一次获得工资）
- 虚拟商品系统（头像框、称号、徽章等装饰品可用信用点购买）

---

## 5. 改动文件清单

| 文件 | 操作 | 改动内容 |
|------|------|----------|
| `server/app/services/seed_data.py` | **新建** | `seed_public_memories()` 函数 + `_load_seed_file()` 辅助函数 |
| `server/data/public_memories.json` | **新建** | 10~15 条世界观/规则类种子数据 |
| `server/main.py` | **修改** `lifespan()` | 在 `await init_vector_store()` 之后、`scheduler_task` 之前，添加 `await seed_public_memories()` 调用 |

### 5.1 `server/app/services/seed_data.py` — 新建

```
函数：
  - seed_public_memories() -> None    # 幂等填充入口
  - _load_seed_file() -> list[dict]   # JSON 文件读取

依赖：
  - from ..core.database import async_session
  - from ..models import Memory, MemoryType
  - from . import vector_store
  - from sqlalchemy import select, func as sa_func
  - import json, logging
  - from pathlib import Path
```

### 5.2 `server/main.py` — 修改 `lifespan()`

```python
# 修改前（第 82~89 行）：
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_human_agent()
    await seed_jobs_and_items()
    await seed_city_buildings()
    await init_vector_store()
    scheduler_task = asyncio.create_task(scheduler_loop())

# 修改后：
async def lifespan(app: FastAPI):
    await init_db()
    await ensure_human_agent()
    await seed_jobs_and_items()
    await seed_city_buildings()
    await init_vector_store()
    await seed_public_memories()          # ← 新增：公共记忆种子填充
    scheduler_task = asyncio.create_task(scheduler_loop())
```

新增 import：
```python
from app.services.seed_data import seed_public_memories
```

注意：`seed_public_memories()` 必须在 `init_vector_store()` 之后调用，因为 embedding 生成依赖 vector_store 的 httpx client 初始化。

### 5.3 `server/data/public_memories.json` — 新建

纯 JSON 数组，10~15 个对象，每个对象仅含 `content` 字段。

### 5.4 不改动文件

| 文件 | 原因 |
|------|------|
| `server/app/services/memory_service.py` | 不复用 `save_memory()`，seed 函数自行管理批量事务 |
| `server/app/services/vector_store.py` | 直接调用已有 `upsert_memory()` 和 `embed()`，无需修改 |
| `server/app/models/tables.py` | Memory 表已有 PUBLIC 类型支持，无需改动 |
| `server/app/api/memories.py` | 管理 API 已存在，无需新增 |

---

## 6. 幂等逻辑详细说明

```
启动时 → seed_public_memories()
  ├─ DB 中 public 记忆 count > 0 → 跳过（info log）
  └─ DB 中 public 记忆 count == 0 → 执行填充
       ├─ JSON 文件不存在 → 跳过（warning log）
       ├─ JSON 解析失败 → 跳过（warning log）
       └─ 正常读取 → 逐条处理
            ├─ content 为空/纯空白 → 跳过该条
            ├─ embedding 成功 → 计入 success
            └─ embedding 失败 → warning log + 跳过该条，继续下一条
```

边界场景：
- **首次启动，embedding 服务不可用**：所有条目 embedding 失败，全部跳过，DB 中 0 条公共记忆。下次启动时 count=0，会重新尝试填充 — 自愈
- **首次启动，部分 embedding 失败**：成功 N 条写入 DB。下次启动时 count=N > 0，跳过 — 不会重复填充，但也不会补齐失败的条目。这是可接受的行为（管理员可通过 `DELETE /api/memories/{id}` 清空后重启来触发重新填充，或通过 `POST /api/memories` 手动补充）
- **JSON 文件被删除**：`_load_seed_file()` 返回空列表，不插入任何数据，不报错

---

## 7. 错误处理

| 场景 | 处理方式 | 日志级别 |
|------|----------|----------|
| JSON 文件不存在 | 返回空列表，不填充 | WARNING |
| JSON 解析失败（格式错误） | 返回空列表，不填充 | WARNING |
| 单条 content 为空字符串 | 跳过该条 | DEBUG |
| 单条 embedding API 调用失败 | 跳过该条，继续下一条 | WARNING |
| 单条 embedding API 超时 | 同上（httpx 30s 超时由 vector_store client 控制） | WARNING |
| DB commit 失败 | 异常上抛，由 lifespan 捕获（不应 swallow） | ERROR |
| vector_store 未初始化 | `embed()` 抛 RuntimeError，被 try/except 捕获，该条跳过 | WARNING |

关键约束：**任何单条失败都不阻塞服务启动**。只有 DB 级别的致命错误（如磁盘满）才会上抛。

---

## 8. 测试用例

### 8.1 单元测试（UT）

文件：`server/tests/test_seed_public_memories.py`

所有 UT mock 掉 `vector_store.upsert_memory`，使用内存 SQLite（conftest 中的 `db` fixture）。

```python
# --- 幂等逻辑 ---

@pytest.mark.asyncio
async def test_seed_skips_when_public_memories_exist(db):
    """DB 中已有公共记忆时，seed_public_memories 不插入新数据。

    前置：手动插入 1 条 memory_type='public' 的记录
    断言：调用后 public 记忆数量不变（仍为 1）
    """

@pytest.mark.asyncio
async def test_seed_inserts_when_no_public_memories(db, tmp_path):
    """DB 为空时，seed_public_memories 从 JSON 读取并插入。

    前置：创建临时 JSON 文件（3 条），mock vector_store.upsert_memory 为 no-op
    断言：DB 中 public 记忆数量 == 3，每条 content 与 JSON 一致
    """

@pytest.mark.asyncio
async def test_seed_idempotent_on_double_call(db, tmp_path):
    """连续调用两次，第二次不插入重复数据。

    前置：创建临时 JSON 文件（3 条）
    断言：两次调用后 DB 中 public 记忆数量仍为 3
    """

# --- embedding 失败处理 ---

@pytest.mark.asyncio
async def test_seed_skips_failed_embedding(db, tmp_path):
    """单条 embedding 失败时跳过该条，其余正常插入。

    前置：JSON 3 条，mock upsert_memory 第 2 条抛 RuntimeError
    断言：DB 中 public 记忆数量 == 2（跳过失败的 1 条）
    """

@pytest.mark.asyncio
async def test_seed_all_embedding_fail_inserts_nothing(db, tmp_path):
    """所有 embedding 都失败时，DB 中 0 条公共记忆。

    前置：JSON 3 条，mock upsert_memory 全部抛异常
    断言：DB 中 public 记忆数量 == 0
    """

# --- JSON 文件异常 ---

@pytest.mark.asyncio
async def test_seed_missing_json_file(db):
    """JSON 文件不存在时，不插入数据，不抛异常。

    前置：mock _load_seed_file 的文件路径指向不存在的路径
    断言：DB 中 public 记忆数量 == 0，无异常抛出
    """

@pytest.mark.asyncio
async def test_seed_invalid_json(db, tmp_path):
    """JSON 格式错误时，不插入数据，不抛异常。

    前置：创建内容为 '{invalid' 的文件
    断言：DB 中 public 记忆数量 == 0，无异常抛出
    """

@pytest.mark.asyncio
async def test_seed_empty_content_skipped(db, tmp_path):
    """content 为空字符串或纯空白的条目被跳过。

    前置：JSON 含 [{"content": ""}, {"content": "  "}, {"content": "有效内容"}]
    断言：DB 中 public 记忆数量 == 1
    """

# --- 数据完整性 ---

@pytest.mark.asyncio
async def test_seed_memory_fields_correct(db, tmp_path):
    """插入的记忆字段值正确。

    前置：JSON 1 条 {"content": "测试内容"}
    断言：
      - memory.agent_id is None
      - memory.memory_type == MemoryType.PUBLIC
      - memory.content == "测试内容"
      - memory.expires_at is None
      - memory.access_count == 0
    """

@pytest.mark.asyncio
async def test_seed_calls_upsert_with_correct_agent_id(db, tmp_path):
    """upsert_memory 调用时 agent_id 传 -1（公共记忆标识）。

    前置：JSON 1 条，mock upsert_memory
    断言：mock_upsert.assert_awaited_once_with(ANY, -1, "内容", db)
    """
```

### 8.2 系统测试（ST）

文件：`server/tests/test_st_seed_public_memories.py`

ST 需要真实的 embedding API（或 mock 整个 httpx client 返回合法 embedding）。

```python
@pytest.mark.asyncio
async def test_st_seed_creates_searchable_memories(db):
    """ST：种子数据插入后可通过向量检索召回。

    前置：
      - mock vector_store.embed 返回固定非零向量
      - 调用 seed_public_memories()
    断言：
      - DB 中 public 记忆 count >= 10
      - 每条记忆的 embedding 字段非 None
      - 每条记忆的 embedding 长度 == embedding_dim * 4
    """

@pytest.mark.asyncio
async def test_st_seed_not_block_startup_on_embedding_failure(db):
    """ST：embedding 服务完全不可用时，服务仍能正常启动。

    前置：mock vector_store.embed 抛 httpx.ConnectError
    断言：seed_public_memories() 正常返回（不抛异常），DB 中 public 记忆 count == 0
    """

@pytest.mark.asyncio
async def test_st_public_memories_in_agent_search(db):
    """ST：Agent 搜索记忆时能召回公共记忆。

    前置：
      - 插入 1 条 public 记忆（带 embedding）
      - mock search_memories 返回该条
    断言：memory_service.search(agent_id=1, query="...", db=db) 结果包含该公共记忆
    """
```

---

## 9. 参考文件

| 文件 | 用途 |
|------|------|
| `server/main.py` | lifespan 启动逻辑，seed 调用位置参考 |
| `server/app/services/memory_service.py` | `save_memory()` 接口参考（不直接复用） |
| `server/app/services/vector_store.py` | `embed()` / `upsert_memory()` 调用方式 |
| `server/app/models/tables.py` | Memory 表结构、MemoryType 枚举 |
| `server/app/core/database.py` | `async_session` 工厂 |
| `server/app/core/config.py` | `settings.embedding_dim` |
| `server/tests/conftest.py` | 测试 db fixture |
| `server/tests/test_memory_service.py` | 测试模式参考（mock vector_store） |

---

## 10. 约束与注意事项

1. `seed_public_memories()` 必须在 `init_vector_store()` 之后调用 — embedding 依赖 httpx client
2. JSON 文件使用 UTF-8 编码，内容全中文
3. 种子数据不含通用知识（编程、数学等），仅限 OpenClaw 世界观/规则（DC-9）
4. 后续增删公共记忆通过已有管理 API（`POST /api/memories`、`DELETE /api/memories/{id}`），不修改 JSON 文件（DC-10）
5. embedding 失败的条目不会在下次启动时自动补齐（幂等判断为 count > 0 即跳过）— 这是有意的简化设计，管理员可手动处理

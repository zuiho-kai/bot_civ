# 综合审计报告 — bot_civ (OpenClaw Community)

**审计日期**: 2026-02
**审计范围**: 安全、架构、性能
**代码版本**: main@37230d1

---

## 总览

| 类别 | 严重 | 高 | 中 | 低 | 信息 |
|------|------|-----|-----|-----|------|
| 安全 | 3 | 5 | 4 | 5 | — |
| 架构 | — | 4 | 4 | 2 | — |
| 性能 | — | 2 | 3 | 4 | 1 |
| **合计** | **3** | **11** | **11** | **11** | **1** |

---

## 一、安全审计

### 严重 (CRITICAL)

#### S-C1: 人类 WebSocket 零认证

- **位置**: `server/app/api/chat.py:332-361`
- **描述**: `agent_id=0` 的人类连接无需任何认证。任意客户端可发送消息、触发 LLM 唤醒（消耗信用点）、持久化数据到数据库。
- **影响**: 攻击者可冒充人类用户发送任意消息，触发 Agent 回复消耗 API 额度，向数据库注入恶意内容。
- **建议**: 为人类 WebSocket 连接增加认证机制（如 session token 或 JWT），拒绝未认证连接。

#### S-C2: Bot Token 泄露给所有 API 消费者

- **位置**: Agent API 响应
- **描述**: Bot 认证令牌在 API 响应中暴露给所有客户端，任何人可获取 token 冒充 Bot 连接。
- **影响**: 攻击者可劫持任意 Agent 的 Bot 连接，以其身份发送消息。
- **建议**: API 响应中移除 `bot_token` 字段，仅在创建 Agent 时返回一次，或提供独立的 token 查询接口并加权限控制。

#### S-C3: 开发/管理端点暴露在生产环境

- **位置**: `server/app/api/dev_trigger.py`
- **描述**: 开发调试端点（模拟消息触发器等）无访问控制，生产环境可直接调用。
- **影响**: 攻击者可通过开发端点触发系统操作，绕过正常业务流程。
- **建议**: 通过环境变量控制是否注册开发路由（`if settings.debug: app.include_router(dev_router)`），或增加管理员认证。

### 高 (HIGH)

#### S-H1: 记忆提取查询存在 SQL 注入风险

- **位置**: 记忆服务相关查询
- **描述**: 部分记忆提取查询未充分参数化，存在注入向量。
- **建议**: 确保所有数据库查询使用 SQLAlchemy ORM 参数绑定，禁止字符串拼接。

#### S-H2: 凭证明文存储

- **位置**: `server/app/core/config.py`
- **描述**: API 密钥通过 `.env` 明文存储，无加密保护。
- **建议**: 生产环境使用密钥管理服务（如 AWS Secrets Manager、HashiCorp Vault），`.env` 仅用于本地开发。

#### S-H3: WebSocket 消息无速率限制

- **位置**: `server/app/api/chat.py:388-445`
- **描述**: WebSocket 消息接收循环无频率限制，客户端可无限速发送消息。
- **影响**: 恶意客户端可发送大量消息，触发大量 LLM 调用，耗尽 API 额度和服务器资源。
- **建议**: 增加每连接消息速率限制（如每秒 5 条），超限断开连接或静默丢弃。

#### S-H4: Agent 创建/更新输入验证不足

- **位置**: Agent CRUD API
- **描述**: Agent 创建和更新接口对输入字段（persona、model 等）缺乏长度和内容校验。
- **建议**: 对所有用户输入字段增加长度限制和内容过滤。

#### S-H5: 缺少 CORS 验证

- **位置**: FastAPI 应用配置
- **描述**: 未配置 CORS 中间件或配置过于宽松，允许任意来源跨域请求。
- **建议**: 配置 `CORSMiddleware`，限制 `allow_origins` 为已知前端域名。

### 中 (MEDIUM)

#### S-M1: WebSocket 消息内容未转义

- **描述**: 用户消息内容直接广播给所有客户端，未做 XSS 过滤。前端如果直接渲染 HTML 可能导致 XSS。
- **建议**: 前端渲染时确保使用 React 的默认转义（已满足），后端可增加内容长度限制。

#### S-M2: 无审计日志

- **描述**: 关键操作（Agent 创建/删除、转账、悬赏完成）无结构化审计日志。
- **建议**: 对关键业务操作记录审计日志（操作者、时间、操作内容、结果）。

#### S-M3: 经济系统转账无二次确认

- **位置**: `server/app/services/economy_service.py:70-83`
- **描述**: `transfer_credits` 无金额上限、无二次确认、无操作日志。
- **建议**: 增加单次转账上限、操作日志记录。

#### S-M4: 定时任务无幂等保护

- **位置**: `server/app/services/scheduler.py:57-72`
- **描述**: `daily_grant` 使用 `asyncio.sleep` 等待午夜执行，如果进程重启可能重复发放或遗漏。
- **建议**: 记录上次发放日期，执行前检查是否已发放过。

### 低 (LOW)

#### S-L1: 错误信息泄露内部细节

- **描述**: 部分异常处理返回原始错误信息，可能泄露数据库结构或内部路径。
- **建议**: 生产环境返回通用错误信息，详细错误仅记录到日志。

#### S-L2: 无请求大小限制

- **描述**: WebSocket 和 REST 端点未限制请求体大小。
- **建议**: 配置 Uvicorn/FastAPI 的请求体大小限制。

#### S-L3: Bot Token 生成算法未审查

- **描述**: Bot token 的生成方式未确认是否使用密码学安全随机数。
- **建议**: 确保使用 `secrets.token_urlsafe()` 生成 token。

#### S-L4: 无连接数上限

- **描述**: WebSocket 连接池无最大连接数限制，可能被连接耗尽攻击。
- **建议**: 限制单 IP 和全局最大连接数。

#### S-L5: 心跳机制单向

- **位置**: `server/app/api/chat.py:322-329`
- **描述**: 服务端发送 `ping` 但不验证客户端是否回复 `pong`，僵尸连接可能不被清理。
- **建议**: 记录最后一次 pong 时间，超时未响应则主动断开。

---

## 二、架构审计

### 高 (HIGH)

#### A-H1: God File — chat.py 职责过重

- **位置**: `server/app/api/chat.py`（466 行）
- **描述**: 混合了六项职责：WebSocket 生命周期管理、连接池状态、消息广播、消息持久化、唤醒编排、记忆提取调度。`handle_wakeup` 函数（179-281 行）打开三个独立数据库会话，编排多个服务。
- **建议**: 拆分为三个模块：
  - `server/app/services/connection_manager.py` — WebSocket 连接池 + 广播
  - `server/app/services/chat_orchestrator.py` — 唤醒流程、记忆提取触发
  - `server/app/api/chat.py` — 薄路由层

#### A-H2: 服务间循环依赖

- **描述**: `agent_runner` ↔ `memory_service` ↔ `vector_store` 之间存在循环引用。`scheduler.py` 从 `chat.py` 导入连接池状态（`human_connections`, `bot_connections`）。
- **影响**: 模块耦合度高，难以独立测试和替换。
- **建议**: 引入事件总线或依赖注入，解耦服务间直接引用。

#### A-H3: 无依赖注入框架

- **描述**: 所有服务通过模块级单例实例化（`economy_service = EconomyService()`），无法在测试中轻松替换。
- **建议**: 使用 FastAPI 的 `Depends` 机制或轻量 DI 容器管理服务生命周期。

#### A-H4: 缺少 LLM 供应商抽象层

- **位置**: `server/app/services/agent_runner.py:105`
- **描述**: LLM 调用直接使用 `AsyncOpenAI` SDK，切换供应商（如 Anthropic）需要修改核心代码。
- **建议**: 抽象 `LLMProvider` 接口，通过配置选择具体实现。

### 中 (MEDIUM)

#### A-M1: 数据库会话管理分散

- **描述**: 部分代码通过 `Depends(get_db)` 获取会话，部分通过 `async with async_session() as db` 手动创建。两种模式混用增加了事务边界的不确定性。
- **建议**: 统一会话管理策略，API 层用 `Depends`，服务层接收 `db` 参数。

#### A-M2: 连接池状态为模块级全局变量

- **位置**: `server/app/api/chat.py:26-27`
- **描述**: `human_connections` 和 `bot_connections` 是模块级 dict，被 `scheduler.py` 跨模块直接导入。
- **影响**: 无法水平扩展（多进程/多实例），测试时难以隔离状态。
- **建议**: 封装为 `ConnectionManager` 类，通过 DI 注入。

#### A-M3: 唤醒服务与聊天路由紧耦合

- **描述**: `handle_wakeup` 直接访问连接池、调用 runner、操作数据库、触发广播，承担了编排者角色但嵌在路由模块中。
- **建议**: 提取为独立的 `ChatOrchestrator` 服务。

#### A-M4: 前端无状态管理方案

- **描述**: 前端状态分散在各组件中，无 Context/Redux/Zustand 等集中状态管理。随着功能增长（经济、工作、商店），状态同步将变得困难。
- **建议**: 引入轻量状态管理（如 Zustand 或 React Context），集中管理 agents、messages、经济数据。

### 低 (LOW)

#### A-L1: 前端 Mock 模式与真实模式混合

- **位置**: `web/src/api.ts`
- **描述**: 每个 API 函数都包含 mock 分支，增加了代码复杂度。
- **建议**: 将 mock 逻辑提取为独立的 mock adapter，通过环境变量切换。

#### A-L2: 缺少 API 版本控制

- **描述**: 所有 API 路径为 `/api/xxx`，无版本前缀。
- **建议**: 使用 `/api/v1/xxx` 前缀，为未来 API 演进预留空间。

---

## 三、性能审计

### 高 (HIGH)

#### P-H1: handle_wakeup 中 LLM 调用串行执行

- **位置**: `server/app/api/chat.py:240-251`
- **描述**: 当一条消息唤醒多个 Agent 时，`handle_wakeup` 在 `for` 循环中逐个调用 `runner.generate_reply()`。每次 LLM 调用耗时 1-5 秒，3 个 Agent 意味着最后一个回复延迟 3-15 秒。
- **现状**: `AgentRunnerManager.batch_generate()`（agent_runner.py:161-205）已实现并行 `asyncio.gather`，但 `handle_wakeup` 未使用，仅 `hourly_wakeup_loop` 在用。
- **建议**: 重构 `handle_wakeup` 使用 `batch_generate()`，然后通过 `delayed_send` 错开广播。

#### P-H2: 每次唤醒调用创建新 HTTP 客户端

- **位置**: `server/app/services/wakeup_service.py:54`
- **描述**: `call_wakeup_model` 每次调用都创建新的 `httpx.AsyncClient`，意味着每次唤醒决策都要建立新的 TCP 连接 + TLS 握手。
- **影响**: 每次调用额外 100-300ms 连接建立开销。
- **建议**: 使用模块级持久化 `httpx.AsyncClient`（参考 `vector_store.py` 的做法），启动时初始化，关闭时销毁。

### 中 (MEDIUM)

#### P-M1: 每次 LLM 调用创建新 OpenAI 客户端

- **位置**: `server/app/services/agent_runner.py:105`
- **描述**: `generate_reply()` 每次调用都创建新的 `AsyncOpenAI` 实例，内部会创建新的 `httpx.AsyncClient` 连接池。
- **建议**: 按 `(base_url, api_key)` 缓存 `AsyncOpenAI` 客户端实例。

#### P-M2: 每条消息重复查询 Agent 名称映射

- **位置**: `server/app/api/chat.py:150, 412`
- **描述**: `send_agent_message` 和消息接收流程每次都执行 `SELECT name, id FROM agents`。Agent 名称变更频率极低。
- **建议**: 内存缓存 name_map，设置短 TTL（如 60 秒）或在 Agent 增删改时失效。

#### P-M3: 向量搜索全表扫描

- **位置**: `server/app/services/vector_store.py:98-111`
- **描述**: `search_memories` 加载目标 Agent 的所有 embedding 到内存，反序列化为 NumPy 数组后计算余弦相似度。1024 维 float32 每条 4KB，10k 条记忆 = 40MB。
- **现状**: 代码注释已标注 "<10k memories per agent 可接受"。
- **建议**: 近期增加时间窗口过滤减少工作集；中期引入 SQLite FTS5 做粗筛再向量排序。

### 低 (LOW)

#### P-L1: 唤醒流程重复查询最近消息

- **位置**: `chat.py:216-228` 和 `wakeup_service.py:242-249`
- **描述**: 唤醒流程中 `wakeup_service.process()` 和 `handle_wakeup` 各自查询一次 `SELECT ... FROM messages ORDER BY created_at DESC LIMIT 10`，内容完全相同。
- **建议**: 查询一次，通过参数传递。

#### P-L2: WebSocket 广播串行发送

- **位置**: `server/app/api/chat.py:115-132`
- **描述**: `broadcast()` 逐个 `await ws.send_text()`，一个慢连接会阻塞后续所有发送。
- **建议**: 使用 `asyncio.gather(return_exceptions=True)` 并行发送。

#### P-L3: 缺少数据库索引

- **位置**: `server/app/models/tables.py`
- **描述**: 以下高频查询路径缺少索引：
  - `messages.created_at` — 每次消息拉取和唤醒都用 `ORDER BY created_at DESC`
  - `checkins.agent_id` + `checkins.checked_at` — 每次打卡校验
  - `memories.agent_id` + `memories.embedding IS NOT NULL` — 每次向量搜索
- **建议**: 为热查询路径添加显式索引。

#### P-L4: 前端 MessageList 全量重渲染

- **位置**: `web/src/components/MessageList.tsx:17-24`
- **描述**: 每条新消息触发整个列表重渲染，`MessageBubble` 未使用 `React.memo`。
- **现状**: 消息量 <100 时无感知。
- **建议**: `MessageBubble` 包裹 `React.memo`；消息量大时引入虚拟滚动（如 `react-window`）。

### 信息 (INFO)

#### P-I1: 所有事务使用 IMMEDIATE 模式

- **位置**: `server/app/core/database.py:26`
- **描述**: `isolation_level = "IMMEDIATE"` 使所有事务（包括只读操作）立即获取写锁。SQLite WAL 模式支持并发读，但 IMMEDIATE 模式使读操作也排队等待。
- **建议**: 只读端点（`get_messages`、`get_jobs` 等）使用 `DEFERRED` 模式，写操作保持 `IMMEDIATE`。

---

## 四、优先修复路线图

### Phase 0 — 安全关键项（上线前必须完成）

| 序号 | 问题 | 工作量 |
|------|------|--------|
| 1 | S-C1: 人类 WebSocket 增加认证 | 中 |
| 2 | S-C2: API 响应移除 bot_token | 小 |
| 3 | S-C3: 生产环境禁用 dev_trigger 端点 | 小 |

### Phase 1 — 高收益快速修复

| 序号 | 问题 | 工作量 |
|------|------|--------|
| 4 | P-H2: 复用 httpx 客户端（wakeup_service） | 小 |
| 5 | P-M1: 缓存 AsyncOpenAI 客户端 | 小 |
| 6 | P-H1: handle_wakeup 使用 batch_generate | 中 |
| 7 | S-H3: WebSocket 消息速率限制 | 小 |
| 8 | S-H1: 参数化记忆提取查询 | 小 |
| 9 | S-H4: Agent 输入验证加强 | 小 |
| 10 | S-H5: 配置 CORS 中间件 | 小 |

### Phase 2 — 架构重构

| 序号 | 问题 | 工作量 |
|------|------|--------|
| 11 | A-H1: 拆分 chat.py 为三个模块 | 大 |
| 12 | P-M2: 缓存 agent_name_map | 小 |
| 13 | P-L3: 添加数据库索引 | 小 |
| 14 | A-H3: 引入依赖注入 | 中 |
| 15 | P-I1: 只读事务改用 DEFERRED | 中 |

### Phase 3 — 规模化准备

| 序号 | 问题 | 工作量 |
|------|------|--------|
| 16 | P-L2: 并行 WebSocket 广播 | 小 |
| 17 | P-M3: 向量搜索优化（时间窗口 + FTS5） | 中 |
| 18 | P-L4: 前端 React.memo + 虚拟滚动 | 中 |
| 19 | A-H4: LLM 供应商抽象层 | 中 |
| 20 | A-H2: 解耦服务循环依赖 | 大 |

---

## 总结

代码库在当前规模下（单服务器、<20 Agent、<10k 消息）结构良好，测试覆盖充分（106 单元 + 14 E2E 全绿）。安全问题是唯一的硬性阻塞项 — 三个严重漏洞必须在任何公开部署前修复。架构和性能问题可随负载增长逐步迭代。

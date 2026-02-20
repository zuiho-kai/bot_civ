# IR-M6.2 原型对齐补丁包

> 状态：评审修订版（五方评审完成，用户拍板完成）
> 目标：原型完成度提升，消除 4 项核心体验 gap

---

## 背景

M1~M6.1 已完成核心功能闭环（聊天群、唤醒、经济、城市、交易、建造、策略自动机）。原型需求差距评估发现 4 项 gap 影响核心体验，需补齐后才能进入演示/内测阶段。

这 4 项均为现有框架的增强/填充，不涉及新架构引入。

---

## P1：记忆提取质量优化

### 现状

`chat.py:_extract_memory()` 每 5 轮对话触发一次记忆提取，当前实现：
```python
combined = "\n".join(f"{m.get('name','?')}: {m.get('content','')}" for m in recent[-5:])
summary = f"对话摘要: {combined[:200]}"  # 硬截断 200 字符
```

问题：
- 无语义压缩，直接拼接原文
- 硬截断 200 字符，可能截断关键信息（如"我喜欢猫"截成"我喜欢"）
- 生成的记忆质量低，向量检索召回后对 Agent 回复帮助有限

### 目标

用 LLM 对最近 5 轮对话做语义摘要，生成 1~2 句高质量记忆条目。

### 功能要求

1. 在 `MODEL_REGISTRY` 中注册 `memory-summary-model` 条目（默认指向 wakeup-model 同款 gemma-3-12b），复用现有模型注册机制
2. 摘要 prompt 要求：提取关键事实/偏好/承诺，忽略寒暄，输出 ≤100 字
3. LLM 调用采用 fallback 链：主模型（memory-summary-model）超时/失败 → 备用模型（硅基流动其他免费模型）→ 截断拼接兜底
4. LLM 调用超时 = 15 秒，使用 `asyncio.wait_for()` 包裹
5. 两个调用点（`handle_wakeup` 和 `delayed_send`）统一改为 fire-and-forget（`asyncio.create_task`），记忆提取不阻塞消息发送主流程
6. 摘要结果轻量校验：非空 + 长度 ≥5 字，不通过则走 fallback

### 改动范围

| 文件 | 改动 |
|------|------|
| `server/app/api/chat.py` | `_extract_memory()` 改为调用 LLM 摘要，`delayed_send` 中改为 fire-and-forget |
| `server/app/core/config.py` | `MODEL_REGISTRY` 新增 `memory-summary-model` 条目 |

> 不抽取公共 LLM 调用函数 — 直接在 `chat.py:_extract_memory()` 内部轻量调用 `AsyncOpenAI`，复用 `resolve_model` 获取配置即可，避免不必要的耦合。

### 验收标准

- AC-1：正常情况下记忆内容由 LLM 生成，不等于 `对话摘要: {原文[:200]}` 格式，且长度 ≤100 字
- AC-2：主模型超时（15s）时自动切换备用模型；备用模型也失败时 fallback 到截断拼接，不报错不阻塞
- AC-3：摘要长度 ≤100 字
- AC-4：`MODEL_REGISTRY` 中可配置 `memory-summary-model`
- AC-5：`delayed_send` 中记忆提取为 fire-and-forget，不阻塞消息广播

### 已确认决策

- DC-1：复用 wakeup-model（gemma-3-12b），免费且已验证 ✅
- DC-2：轻量校验（非空 + ≥5 字），不通过走 fallback ✅

---

## P2：SOUL.md 深度人格

### 现状

Agent 表只有一个 `persona` 文本字段，存储一段简短描述（如"你是一个热爱编程的猫娘"）。这种粒度不足以让 Agent 表现出稳定、有深度的人格特征。

### 目标

引入结构化人格定义（SOUL.md 格式），让每个 Agent 拥有：
- 核心价值观 / 说话风格 / 知识领域 / 情感倾向 / 口头禅
- 人际关系偏好（对谁友好/对谁警惕）
- 行为禁区（绝对不会做的事）

### 功能要求

1. Agent 表新增 `personality_json` 字段（`Column(JSON, nullable=True)`）
2. 定义 SOUL schema（Pydantic model），包含：
   - `values`: list[str] — 核心价值观（1~5 条）
   - `speaking_style`: str — 说话风格描述
   - `knowledge_domains`: list[str] — 擅长领域
   - `emotional_tendency`: str — 情感倾向
   - `catchphrases`: list[str] — 口头禅（0~3 条）
   - `relationships`: dict[str, str] — 对其他 Agent 的态度（可选）
   - `taboos`: list[str] — 行为禁区（0~3 条）
3. `personality_json` 与 `persona` 共存，`personality_json` 优先。有 `personality_json` 时用结构化格式注入 system prompt，否则用 `persona` 文本（向后兼容）
4. API 层：创建/更新 Agent 时支持 `personality_json` 字段
5. 前端：AgentManager 页面只读展示 personality_json（M6.2 不做编辑功能）

### Schema 校验策略（M6.2 Lenient 模式）

- 所有字段 optional（空 JSON `{}` 合法）
- 超限（如 values > 5 条）：截断并写 warning log（字段名 + 原始值 + 处理方式）
- 未知字段：忽略并写 warning log（`model_config = {"extra": "ignore"}`）
- **业务强约束 reject**：relationships 引用不存在的 Agent name → 400 拒绝；字段值类型错误（如 values 传入非字符串）→ 400 拒绝

> **Schema 演进路线图**：M6.2 lenient 模式 → M6.3 收紧为 strict（超限拒绝、未知字段拒绝、新增 version 字段）

### M6.2 / M6.3 范围划分

| 阶段 | 范围 |
|------|------|
| M6.2 | 后端 schema + prompt 注入 + AgentManager 只读展示 + 编辑走 API |
| M6.3 | JSON 编辑器 + 表单优化 + 字段级校验 |

### 改动范围

| 文件 | 改动 |
|------|------|
| `server/app/models/tables.py` | Agent 表新增 `personality_json` 字段（`Column(JSON)`） |
| `server/app/api/schemas.py` | AgentCreate/AgentUpdate/AgentOut 扩展 |
| `server/app/services/agent_runner.py` | system prompt 注入逻辑（personality_json 优先，persona fallback） |
| `server/app/api/agents.py` | CRUD 支持新字段 |
| `web/src/types.ts` | Agent 接口扩展 |
| `web/src/pages/AgentManager.tsx` | 只读展示结构化人格信息 |

> 无需 DB migration — Agent 表当前不存在，`create_all` 直接建出带新字段的表。

### 验收标准

- AC-1：创建 Agent 时可传入 personality_json，存储到 DB
- AC-2：有 personality_json 的 Agent，system prompt 使用结构化人格（非简单 persona）
- AC-3：无 personality_json 的 Agent，行为不变（向后兼容）
- AC-4：前端 AgentManager 只读展示结构化人格信息
- AC-5：personality_json 格式校验 — lenient 模式，silent 修正写 warning log，业务强约束 reject
- AC-6：空 JSON `{}` 传入不报错，等同于无 personality_json

### 已确认决策

- DC-3：共存，personality_json 优先，persona 作 fallback ✅
- DC-4：M6.2 不做预设人格模板 ✅
- DC-5：M6.2 只读展示，编辑走 API；M6.3 做 JSON 编辑器 + 表单 ✅

---

## P3：悬赏 Agent 自主接取

### 现状

悬赏系统 CRUD + 前端 UI 已完整实现（M2 Phase 5），但 Agent 自主决策引擎（`autonomy_service.py`）完全不知道悬赏的存在：
- `build_world_snapshot()` 不包含悬赏数据
- `SYSTEM_PROMPT` 行为列表无 `claim_bounty`
- `execute_decisions()` 无悬赏执行分支
- `_validate_actions()` 白名单无 `claim_bounty`
- `tool_registry.py` 无悬赏工具

### 目标

让 Agent 能在自主决策循环中浏览开放悬赏、决定是否接取。M6.2 只做接取（claim），完成仍由人工/管理 API 操作。

### 设计哲学：意图-执行分离

- **决策层（LLM）**：不硬编码前置条件，Agent 可自由浏览所有悬赏并自主判断是否接取
- **执行层（bounty_service）**：原子校验兜底 — 已有进行中悬赏 → 拒绝，悬赏已被接 → 拒绝（先到先得）
- **提示层（SYSTEM_PROMPT）**：自然语言引导 — "你同时只能接取一个悬赏，接取前考虑竞争概率"
- **失败处理**：claim 失败消耗完整 tick（与 purchase/checkin 失败行为一致），失败原因写入上一轮行为板块，LLM 下轮可见

> **防振荡机制**（M6.3 技术债）：tick 去同步、冷却时间、竞争概率感知 — 20 Agent 原型阶段振荡风险可控，高级机制留后续。

### 功能要求

1. `build_world_snapshot()` 新增悬赏板块（开放 + 进行中的悬赏列表）
2. `SYSTEM_PROMPT` 新增 `claim_bounty` 行为及触发规则
3. `_validate_actions()` 白名单新增 `claim_bounty`
4. `execute_decisions()` 新增 `claim_bounty` elif 执行分支
5. 抽取 `bounty_service.py`（从 `bounties.py` API 层抽取业务逻辑，供 autonomy 复用）
6. `bounty_service` 事务策略：不自行 commit，由调用方（API endpoint 或 autonomy tick）统一 commit/rollback（与 market_service/city_service 一致）
7. `tool_registry.py` 注册 `claim_bounty` 工具（供 Agent 对话时调用）
8. 悬赏状态变更时由 autonomy_service 广播 WebSocket 事件（复用已有 `_broadcast_action` 模式，不引入反向依赖）

### 改动范围

| 文件 | 改动 |
|------|------|
| `server/app/services/autonomy_service.py` | 世界快照 + SYSTEM_PROMPT + `_validate_actions` 白名单 + `execute_decisions` 分支 + WebSocket 广播 |
| `server/app/services/bounty_service.py` | 新建，抽取业务逻辑（不自行 commit） |
| `server/app/services/tool_registry.py` | 注册 claim_bounty 工具 |
| `server/app/api/bounties.py` | 重构为调用 bounty_service |

### 验收标准

- AC-1：Agent 世界快照包含开放悬赏列表
- AC-2：Agent 自主决策可输出 claim_bounty 行为（不被 `_validate_actions` 过滤）
- AC-3：claim_bounty 执行成功后悬赏状态变为 claimed
- AC-4：Agent 对话中可通过 tool_call 接取悬赏
- AC-5：悬赏状态变更广播 WebSocket 事件
- AC-6：已被接取的悬赏不可重复接取（原子校验，先到先得）
- AC-7：原有悬赏 CRUD API 行为不变（回归保证）
- AC-8：悬赏状态变更与 WebSocket 广播解耦，广播失败不回滚状态
- AC-9：同一 Agent 已有进行中悬赏时，claim 新悬赏被拒绝

### 已确认决策

- DC-6：M6.2 只做接取（claim），不做 complete_bounty 自主完成 ✅
- DC-7：不硬编码前置条件，执行层原子校验兜底，失败消耗完整 tick，SYSTEM_PROMPT 自然语言引导 ✅
- DC-8：同一 Agent 同时最多接取 1 个悬赏 ✅

---

## P4：公共记忆知识库填充

### 现状

公共记忆框架完整（MemoryType.PUBLIC、agent_id=NULL、向量检索包含公共记忆、agent_runner 分区展示"公共知识"），但数据库中 `memory_type='public'` 记录数 = 0。

`main.py` lifespan 有 `seed_jobs_and_items()` 和 `seed_city_buildings()` 但没有 `seed_public_memories()`。

管理 API `POST /api/memories` 和 `DELETE /api/memories/{id}` 已存在。

### 目标

填充初始公共知识库（纯世界观/规则类），让 Agent 对话时能引用共享知识。

### 功能要求

1. 新建 `seed_public_memories()` 函数，在 lifespan 启动时填充初始公共记忆
2. 种子数据内容：纯世界观/规则类 — 城市规则、经济系统说明、社区公约、常见问题（不含通用知识如编程常识，Agent 的 LLM 本身已有）
3. 种子数据 10~15 条起步，用 JSON 文件存储（方便非开发人员编辑）
4. 幂等设计：已有公共记忆时跳过（防止重复填充）
5. 种子数据 embedding 生成失败时跳过该条并写 warning log，不阻塞服务启动

### 改动范围

| 文件 | 改动 |
|------|------|
| `server/app/services/seed_data.py` | 新增 `seed_public_memories()` 函数 |
| `server/data/public_memories.json` | 新建，种子数据定义 |
| `server/main.py` | lifespan 调用 `seed_public_memories()` |

> `DELETE /api/memories/{id}` 已存在，无需新增。

### 验收标准

- AC-1：服务启动后公共记忆表有 ≥10 条种子数据
- AC-2：`memory_service.search()` 传入 `include_public=True` 时返回结果包含公共记忆（UT 级别，mock embedding）
- AC-3：种子数据的 embedding 非全零向量（数据完整性校验）
- AC-4：重复启动不会重复插入
- AC-5：单条种子数据 embedding 生成失败时跳过该条，不阻塞启动，写 warning log

### 已确认决策

- DC-9：纯世界观/规则类，不含通用知识 ✅
- DC-10：10~15 条起步，后续通过管理 API 增删 ✅

---

## 优先级与依赖

```
P4（知识库填充）──→ 无依赖，最轻量
P1（记忆提取）──→ 无依赖，改 1 个函数
P2（深度人格）──→ 无依赖，跨模块
P3（悬赏接取）──→ 无依赖，跨模块
```

四项互不依赖，可并行开发。建议按 P4 → P1 → P2/P3 顺序推进（轻量先行，快速出成果）。

---

## 不在范围

- 游戏币（第二货币）— 原型阶段信用点够用
- 模型切换消耗信用点 — 锦上添花
- 头像装饰/皮肤 — 纯装饰性
- F34 长任务编排 — 复杂度高，归入 M6.3
- F33 代码执行沙箱 — 安全风险高，归入 M6.3
- `complete_bounty` 自主完成 — 验证逻辑复杂，归入 M6.3
- 防振荡高级机制（tick 去同步、冷却、竞争概率感知）— 原型阶段风险可控，归入 M6.3
- personality_json 前端编辑（JSON 编辑器 + 表单 + 字段级校验）— 归入 M6.3
- personality_json strict 校验模式 — 归入 M6.3
- Agent 对话 LLM 调用超时控制 — 硅基流动稳定性好，不急，记为技术债

---

## 五方评审记录

评审日期：2026-02-20
评审方：Architect / Tech Lead / Developer / QA Lead / Human Proxy PM

### 已按共识修订（无分歧，直接执行）

| # | 问题 | 来源 | 处理 |
|---|------|------|------|
| 1 | P3 `_validate_actions` 白名单遗漏 | Developer | P3 功能要求 + 改动范围已补充 |
| 2 | P1 LLM 调用缺超时/并发控制 | Architect + Tech Lead + QA | 超时 15s + 备用模型 + fire-and-forget 已写入 |
| 3 | P3 bounty_service 事务边界 | Architect + Developer + Tech Lead | 不自行 commit，已写入功能要求 |
| 4 | P1 摘要模型配置应复用 MODEL_REGISTRY | Architect | 已改为注册 memory-summary-model 条目 |
| 5 | P3 WebSocket 广播依赖方向 | Developer + Tech Lead | 由 autonomy_service 广播，已写入 |
| 6 | P3 缺负面测试 AC | QA Lead | AC-7/8/9 已补充 |
| 7 | P4 AC-4 不可稳定测试 | QA Lead | 已拆为 UT 级可断言 AC |
| 8 | P4 embedding 失败阻塞启动 | Developer + Architect | 失败跳过已写入功能要求 + AC-5 |
| 9 | P4 DELETE 接口已存在 | Tech Lead | 已从改动范围移除 |

### 用户拍板决策

| # | 决策 | 结论 |
|---|------|------|
| 1 | P2 DB migration | 不需要，表不存在，create_all 直接建 |
| 2 | P2 system prompt 长度控制 | 不处理，128k context 无需限制 |
| 3 | P2 schema 校验模式 | lenient + silent 修正可观测 log + 业务强约束 reject + 路线图 |
| 4 | P2 前端范围 | M6.2 只读展示，M6.3 编辑能力 |
| 5 | P3 接取触发条件 | 不硬编码前置条件，执行层原子校验，失败消耗完整 tick |
| 6 | P1 LLM 超时时长 | 15s + 备用模型 fallback 链 |

# AR-P2：SOUL.md 深度人格 — 架构评审

> 状态：待评审
> 对应 SR：SR-P2-SOUL深度人格
> 评审日期：2026-02-20

---

## 1. 架构决策记录（ADR）

### ADR-1：存储方案 — JSON 列 vs 独立表

- 决策：Agent 表新增 `personality_json Column(JSON, nullable=True)`
- 背景：结构化人格包含 7 个可选字段，字段间无独立查询/聚合需求
- 备选：独立 `agent_personality` 表（1:1 关系，每字段一列）
- 理由：① 原型阶段 schema 不稳定，JSON 列增删字段零 DDL 成本 ② 读写始终跟随 Agent 主记录，无 JOIN 开销 ③ SQLite JSON 支持足够（`json_extract` 可用但本期不需要） ④ 独立表在 M6.3 strict 阶段仍可迁移，当前不过度设计
- 风险：JSON 列无法建索引、无 DB 级约束 → 校验全靠应用层 Pydantic

### ADR-2：共存策略 — personality_json 优先，persona 保底

- 决策：两字段共存，`personality_json` 非空时用 SOUL 模板，否则 fallback 到 `persona`
- 理由：① 向后兼容 — 已有 Agent 无需迁移 ② 渐进式采用 — 用户可逐步为 Agent 配置结构化人格 ③ persona 作为"一句话摘要"仍有展示价值（列表页快速预览）
- 约束：不允许 `personality_json={}` 时走 SOUL 模板（空对象等同无人格，走 persona fallback）

### ADR-3：校验策略 — M6.2 Lenient 模式

- 决策：超限截断 + warning log，未知字段忽略，业务强约束（relationships 引用）reject
- 理由：① 原型阶段优先可用性，降低 API 调用方的对接成本 ② warning log 提供可观测性，为 M6.3 收紧提供数据支撑 ③ relationships 引用校验是数据完整性硬约束，不可宽松
- 演进：M6.3 切换为 strict（超限 400、未知字段 400、新增 version 字段）

### ADR-4：Relationships 校验层级 — API 层而非 Pydantic 层

- 决策：`_validate_relationships()` 放在 `agents.py` API 层，不放 Pydantic validator
- 理由：① 校验需要 DB 查询（`select(Agent.name)`），Pydantic validator 无法注入 AsyncSession ② API 层可统一处理 HTTP 异常语义 ③ 保持 SoulPersonality 为纯数据校验类，无 I/O 副作用

## 2. personality_json 与 persona 共存策略分析

### 2.1 数据流

```
创建/更新 API
  ├─ personality_json 非 null → SoulPersonality 校验 → _validate_relationships() → 存入 DB
  └─ personality_json 为 null → 不存储，persona 字段照常写入

AgentRunner 构造
  ├─ agent.personality_json 非空且非 {} → SOUL_PROMPT_TEMPLATE
  └─ 否则 → SYSTEM_PROMPT_TEMPLATE（persona）

前端展示
  ├─ personality_json 存在 → 渲染结构化卡片
  └─ 否则 → 显示 persona 文本
```

### 2.2 共存期间的一致性问题

- persona 和 personality_json 可能描述不一致（用户改了一个没改另一个）
- M6.2 不做自动同步（复杂度高，收益低）
- 建议：前端 AgentManager 在有 personality_json 时隐藏 persona 编辑入口，引导用户使用结构化字段
- M6.3 可考虑：从 personality_json 自动生成 persona 摘要（LLM 一句话总结）

### 2.3 清空语义

| 传入值 | 语义 | DB 存储 |
|--------|------|---------|
| 不传（exclude_unset） | 不修改 | 保持原值 |
| `null` | 不修改（Optional 默认） | 保持原值 |
| `{}` | 清空结构化人格 | 存入 `{}` |
| `{...有效数据}` | 设置/更新 | 存入校验后的 dict |

> 注意：`{}` 存入后 AgentRunner 判定为"空"，走 persona fallback。这是有意设计 — 允许用户"重置"回简单人格模式。

## 3. Schema 演进：Lenient → Strict 向后兼容性

### 3.1 M6.2 → M6.3 变更清单

| 变更项 | M6.2 行为 | M6.3 行为 | 迁移成本 |
|--------|-----------|-----------|----------|
| 超限字段 | 截断 + warning | 400 拒绝 | 低：改 validator 返回值即可 |
| 未知字段 | 忽略 | 400 拒绝 | 低：`extra="ignore"` → `extra="forbid"` |
| version 字段 | 无 | 必填 | 中：需数据迁移脚本补填 version=1 |
| 空 JSON `{}` | 合法 | 待定（可能要求至少 1 个字段） | 低 |

### 3.2 向后兼容风险

- 已存入 DB 的 personality_json 可能含超限数据（M6.2 截断发生在写入前，DB 中数据已是截断后的，无风险）
- 已存入的未知字段：M6.2 `extra="ignore"` 在 Pydantic 层丢弃，不会写入 DB → 无历史脏数据
- version 字段缺失：M6.3 需要一次性 UPDATE 脚本 `UPDATE agents SET personality_json = json_set(personality_json, '$.version', 1) WHERE personality_json IS NOT NULL`
- 结论：M6.2 的 lenient 设计不会产生需要清洗的历史数据，迁移成本可控

## 4. System Prompt 注入分支复杂度评估

### 4.1 AgentRunner 构造函数签名变更

现有签名：
```python
def __init__(self, agent_id: int, name: str, persona: str, model: str)
```

变更后：
```python
def __init__(self, agent_id: int, name: str, persona: str, model: str, personality_json: dict | None = None)
```

- 默认值 `None` 保证所有现有调用方无需修改即可编译通过
- 影响面：3 个调用点需要传入 `personality_json`

### 4.2 调用方影响面分析

| 调用方 | 文件 | 当前传参 | 需改动 |
|--------|------|----------|--------|
| `chat.py:delayed_send` | `server/app/api/chat.py:245` | `agent_id, name, persona, model` | 需新增 `personality_json=agent.personality_json` |
| `agent_runner.py:batch_generate` | `server/app/services/agent_runner.py:256` | `info["agent_id"], info["agent_name"], info["persona"], info["model"]` | 需新增 `personality_json=info.get("personality_json")` |
| `autonomy_service.py:_execute_chats` | 间接通过 `batch_generate` | `agents_info` dict 需含 `personality_json` | 构造 dict 时从 Agent 对象取值 |

### 4.3 generate_reply 分支复杂度

新增一个 if/else 分支（有 personality_json → SOUL 模板，否则 → 旧模板）。圈复杂度 +1，可接受。

关键约束：分支判定条件必须是 `self.personality_json`（truthy 检查），空 dict `{}` 为 falsy 在 Python 中成立，自然走 persona fallback，与 ADR-2 一致。

### 4.4 AgentRunnerManager 缓存失效

`_runners` dict 按 `agent_id` 缓存 Runner 实例。若用户更新了 `personality_json`，缓存中的旧 Runner 仍持有旧值。

- 现有问题：`persona` 更新也有同样的缓存失效问题（已存在的技术债）
- M6.2 处理：不额外处理，与 persona 行为一致。Runner 在下次服务重启或 `remove()` 后重建
- M6.3 建议：`update_agent` 时调用 `runner_manager.remove(agent_id)` 强制重建

## 5. 前端只读展示数据流

```
GET /api/agents/ → AgentOut(personality_json=dict|null) → React state
  └─ AgentManager.tsx
       ├─ personality_json 存在 → <SoulCard> 结构化渲染（值/风格/领域/口头禅/禁区/关系）
       └─ personality_json 为 null → 显示 persona 文本（现有逻辑不变）
```

- 数据量评估：personality_json 单个 Agent 约 200~500 bytes，20 Agent 列表页总增量 < 10KB，无性能顾虑
- 无额外 API 调用：personality_json 随 AgentOut 一并返回，不需要独立接口
- M6.2 不做编辑：前端无 PUT personality_json 的 UI 入口，编辑通过 API 工具（curl/Postman）完成

## 6. JSON 字段 vs 独立表 Trade-off

| 维度 | JSON 列（选定方案） | 独立表 |
|------|---------------------|--------|
| Schema 灵活性 | 高 — 增删字段零 DDL | 低 — 每次加字段需 ALTER TABLE |
| 查询能力 | 弱 — 无法高效 WHERE/INDEX | 强 — 可建索引、JOIN |
| 数据完整性 | 应用层校验 | DB 级 NOT NULL / CHECK |
| 读写性能 | 优 — 随主记录一次 I/O | 需 JOIN 或 eager load |
| 迁移成本 | 低 — 原型阶段无历史数据 | 中 — 需建表 + 外键 |
| M6.3 演进 | 可平滑收紧校验规则 | 已是最终形态 |

结论：原型阶段 Agent 数量 ≤20，无复杂查询需求（不需要"查所有价值观含'善良'的 Agent"），JSON 列是正确选择。若未来需要按人格字段检索（如匹配系统），再迁移到独立表。

## 7. Relationships 校验 N+1 查询风险

### 7.1 当前设计

`_validate_relationships()` 执行一次 `select(Agent.name)` 获取全部 Agent name 集合，再与 `relationships.keys()` 做集合差运算。

### 7.2 查询分析

- 查询次数：固定 1 次（`SELECT name FROM agents`），与 relationships 条目数无关
- 结果集大小：原型阶段 ≤20 Agent，返回 ≤20 行 × 1 列，内存开销可忽略
- 无 N+1 风险：不是逐个 name 查询，而是一次性拉取全集做内存比对

### 7.3 规模化考量（M6.3+）

若 Agent 数量增长到 1000+：
- `select(Agent.name)` 仍然是单次全表扫描，name 列有 unique index，性能可接受
- 可优化为 `select(Agent.name).where(Agent.name.in_(rels.keys()))`，只查引用到的 name，减少传输量
- 当前不做此优化 — 原型阶段过早优化无收益

## 8. 风险评估与缓解

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | Runner 缓存未失效，更新 personality_json 后对话仍用旧人格 | 高 | 中 | M6.2 接受（与 persona 同等技术债）；M6.3 在 update_agent 时 `runner_manager.remove(agent_id)` |
| R2 | SOUL 模板过长导致 token 浪费 | 低 | 低 | 7 个字段全填满约 300~500 字符，远小于 128k context 上限；不做截断 |
| R3 | relationships 引用的 Agent 被删除后，已存储的 personality_json 含悬空引用 | 中 | 低 | M6.2 不做级联清理（读取时 relationships 仅用于 prompt 文本，不做 JOIN）；M6.3 可在 delete_agent 时清理引用方的 relationships |
| R4 | 前端展示 personality_json 时 XSS 风险 | 低 | 高 | React JSX 默认转义；relationships 的 key/value 均为纯文本渲染，不使用 dangerouslySetInnerHTML |
| R5 | M6.3 strict 切换时，已有 API 调用方未适配导致 400 | 中 | 中 | M6.2 warning log 收集超限/未知字段的实际使用情况，M6.3 切换前发布 changelog + 灰度期 |
| R6 | personality_json 与 persona 描述矛盾，Agent 行为不一致 | 中 | 低 | personality_json 存在时完全忽略 persona（不混合注入）；前端引导用户使用结构化字段 |
| R7 | 测试覆盖不足 — 现有 test_memory_injection.py 和 test_batch_generate.py 硬编码 AgentRunner 4 参数构造 | 高 | 中 | 默认参数 `personality_json=None` 保证现有测试不 break；新增 test_agent_runner_soul.py 覆盖 SOUL 路径 |

### 8.1 总体评估

本次改动属于"增量扩展"而非"架构重构"：新增 1 个 DB 字段、1 个 Pydantic model、1 个 prompt 模板、1 个 if/else 分支。影响面可控，最大风险是 R1（缓存失效）和 R7（测试覆盖），均有明确的缓解路径。建议通过 SR 进入编码阶段。

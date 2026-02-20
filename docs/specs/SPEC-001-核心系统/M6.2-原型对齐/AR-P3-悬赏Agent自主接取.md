# AR-P3：悬赏 Agent 自主接取 — 架构评审

> 状态：待评审
> 对应 SR：SR-P3-悬赏Agent自主接取
> 评审日期：2026-02-20

---

## 1. 架构决策记录（ADR）

### ADR-1：抽取 bounty_service 而非在 API 层内联

- 背景：现有 `bounties.py` 将业务逻辑（CAS 更新、状态校验）内联在 endpoint 中，autonomy_service 无法复用
- 决策：新建 `bounty_service.py`，抽取 `claim_bounty()` 为纯业务函数，API 层和 autonomy 层均调用它
- 理由：与 `market_service.py`（挂单/接单/撤单）、`city_service.py`（建造/分配）的分层惯例一致。service 层不感知 HTTP 语义（无 HTTPException），返回 `{"ok": bool, "reason": str}` 统一格式
- 替代方案：在 autonomy_service 中直接 import bounties.py 的 endpoint 函数 — 拒绝，endpoint 函数绑定了 FastAPI 依赖注入（Depends(get_db)），直接调用语义不清且耦合 HTTP 层

### ADR-2：事务策略 — bounty_service 只 flush 不 commit

- 背景：三种调用方对事务边界的需求不同（详见第 4 节）
- 决策：`claim_bounty()` 内部只做 `db.flush()`，commit/rollback 由调用方控制
- 理由：与 `market_service` 的 `create_order`/`accept_order` 模式**不同** — market_service 自行 commit。但 bounty_service 选择不 commit 是因为 autonomy tick 中多个 action 共享同一事务（统一 commit），若 service 自行 commit 会破坏 tick 的事务原子性。这是对现有惯例的**有意偏离**，更接近 `city_service.construct_building` 的模式
- 风险：调用方忘记 commit → 数据丢失。SR 已在事务边界表中明确三种场景的 commit 位置，测试用例 `test_claim_bounty_no_self_commit` 做守护

### ADR-3：CAS 原子校验而非 SELECT FOR UPDATE

- 背景：悬赏接取存在多 Agent 竞争（先到先得）
- 决策：使用 `UPDATE ... WHERE id=X AND status='open'` 的 CAS（Compare-And-Swap）模式，通过 `rowcount == 0` 判断竞争失败
- 理由：SQLite 单写者天然串行，CAS 足够；PostgreSQL 下 CAS 也能正确工作（行级锁隐式获取）。相比 `SELECT FOR UPDATE`（market_service 的做法），CAS 更轻量且不持锁等待
- 与 market_service 的差异说明：market_service 用 `with_for_update()` 是因为接单涉及多表多行修改（冻结释放 + 资源转移 + 订单更新），需要显式锁保证一致性；bounty claim 只改一行，CAS 足矣

### ADR-4：意图-执行分离 — LLM 不做前置校验

- 背景：DC-7 确认不硬编码前置条件
- 决策：SYSTEM_PROMPT 用自然语言引导（"同时只能接取一个"），但不在 LLM 输出校验中拦截。执行层 bounty_service 做原子校验兜底
- 理由：与现有 purchase/checkin 的失败处理一致 — LLM 可能做出"错误"决策，执行层拒绝后失败原因写入 round_log，LLM 下轮可见并自我修正。这是自主性引擎的核心设计哲学

---

## 2. bounty_service 抽取合理性分析

| 维度 | 评估 |
|------|------|
| 职责单一性 | `claim_bounty()` 只做校验 + 状态变更，不含广播/HTTP 语义 — 合理 |
| 返回值格式 | `{"ok": bool, "reason"?: str, "bounty_id"?: int, ...}` — 与 market_service/city_service 一致 |
| 依赖方向 | bounty_service → models（Bounty, Agent）；不依赖 API 层、不依赖 WebSocket — 合理 |
| 可测试性 | 纯 DB 操作，mock db session 即可测试，无外部副作用 — 优秀 |
| 未来扩展 | M6.3 的 `complete_bounty` 自主完成可直接在此 service 中新增函数，无需改架构 |

潜在问题：`bounties.py` 中 `complete_bounty` endpoint 仍内联业务逻辑（原子状态转换 + credits 发放）。SR 明确 M6.2 不动 complete，但 M6.3 应一并抽取到 bounty_service 以保持一致性。建议在 SR 的"不改动文件"表中标注此技术债

---

## 3. autonomy_service 改动影响面

### 3.1 改动点清单

| 函数/常量 | 改动类型 | 影响范围 |
|-----------|----------|----------|
| `SYSTEM_PROMPT` | 追加行为+规则+params | LLM 决策输出格式变化，所有 Agent 的决策循环受影响 |
| `build_world_snapshot()` | 新增第 11 板块 | 快照字符串变长 ~200 字符/悬赏，token 消耗微增 |
| `_validate_actions()` | 白名单追加 1 项 | 纯加法，不影响现有行为 |
| `execute_decisions()` | 新增 elif 分支 | 纯加法，不影响现有 action 的执行路径 |
| `_broadcast_bounty_event()` | 新增函数 | 独立函数，不影响现有代码 |

### 3.2 回归风险评估

- SYSTEM_PROMPT 变更是最大风险点：行为列表和规则列表的变化可能影响 LLM 对其他行为的决策权重。但 claim_bounty 是低频行为（需有开放悬赏），且规则描述明确限制了触发条件，风险可控
- `build_world_snapshot()` 新增板块：纯追加，不修改现有板块的查询逻辑和输出格式
- token 消耗：每个悬赏 ~30 token，20 个悬赏 ~600 token，相对 4000 max_tokens 的输出限制和 128k context 窗口可忽略

### 3.3 不改动的关键路径

- `tick()` 主循环流程不变（快照 → 决策 → 执行）
- `_execute_chats()` 聊天批处理不受影响
- `execute_strategies()` 策略自动机（dormant）不受影响
- F35 状态机（THINKING → EXECUTING → IDLE）流程不变

---

## 4. 事务边界图

### 场景 A：API endpoint 调用

```
HTTP POST /bounties/{id}/claim
  └─ claim_bounty_endpoint()
       ├─ claim_bounty(db=db)        ← service 层，只 flush
       │    ├─ SELECT Bounty
       │    ├─ SELECT Agent
       │    ├─ SELECT count(claimed)
       │    ├─ UPDATE ... WHERE status='open'  ← CAS
       │    └─ db.flush()
       ├─ db.commit()                ← endpoint 控制 commit
       └─ return BountyOut
```

### 场景 B：autonomy tick 调用

```
tick()
  └─ execute_decisions(decisions, db)
       ├─ action="checkin" → ...
       ├─ action="claim_bounty"
       │    ├─ claim_bounty(db=db)   ← service 层，只 flush
       │    ├─ _broadcast_action()   ← 成功时广播 agent_action
       │    └─ _broadcast_bounty_event()  ← 成功时广播 bounty_claimed
       ├─ action="eat" → ...
       └─ db.commit()               ← 所有 action 统一 commit
```

关键：tick 内多个 action 共享同一 db session 和事务。若 claim_bounty 自行 commit，会导致后续 action 的失败无法回滚前面的成功 — 这是 ADR-2 选择"只 flush"的核心原因。

### 场景 C：tool_call 调用

```
agent_runner → tool_registry.execute("claim_bounty", args, context)
  └─ _handle_claim_bounty(args, context)
       ├─ claim_bounty(db=context["db"])  ← service 层，只 flush
       ├─ if ok: db.commit()              ← handler 自行 commit
       └─ return result
```

与 `_handle_transfer_resource` 等现有 handler 一致：tool_call 是独立操作，handler 自行 commit。注意此处广播由前端 WS 事件处理器自动展示，handler 不负责广播。

---

## 5. 并发竞争分析

### 5.1 竞争场景

多个 Agent 在同一 tick 中同时决策 `claim_bounty` 指向同一悬赏。

### 5.2 当前架构下的串行保证

`execute_decisions()` 是**顺序遍历** decisions 列表的（`for dec in decisions:`），不是并发执行。因此同一 tick 内的多个 claim_bounty 实际是串行的：

1. Agent A 的 claim → CAS 成功 → status 变为 claimed（flush 到 session）
2. Agent B 的 claim → CAS 失败（status 已非 open）→ 返回 ok=False

这意味着在 autonomy tick 场景下，**不存在真正的并发竞争**，CAS 的 rowcount 检查足以保证正确性。

### 5.3 跨场景并发

| 场景组合 | 并发可能性 | 保护机制 |
|----------|-----------|----------|
| tick vs tick | 不可能（tick 是定时单线程） | N/A |
| tick vs API | 可能（用户手动 claim + tick 同时执行） | CAS `UPDATE WHERE status='open'`，DB 行级锁保证只有一个成功 |
| tick vs tool_call | 可能（Agent 对话中 tool_call + tick 同时执行） | 同上，CAS 保护 |
| API vs API | 可能（两个用户同时 claim） | 同上，CAS 保护 |

### 5.4 SQLite 特殊性

SQLite 使用数据库级写锁（非行级锁），并发写入时后到者会收到 `SQLITE_BUSY`。SQLAlchemy 的 aiosqlite 驱动默认 `timeout=5` 秒等待锁释放。在 20 Agent 原型规模下，锁竞争概率极低。

### 5.5 DC-8 约束的实现

"同一 Agent 同时最多接取 1 个悬赏"通过 `SELECT count(*) WHERE claimed_by=agent_id AND status='claimed'` 实现。此查询在 CAS UPDATE 之前执行，与 CAS 共享同一事务，不存在 TOCTOU 问题（flush 保证了 session 内可见性）。

---

## 6. WebSocket 广播解耦策略

### 6.1 依赖方向

```
autonomy_service ──→ bounty_service（业务逻辑）
autonomy_service ──→ chat.broadcast（WebSocket 广播）
bounty_service   ✗→  chat.broadcast（不依赖）
```

bounty_service 是纯业务层，不感知 WebSocket 的存在。广播职责由 autonomy_service 的 `_broadcast_bounty_event()` 承担。这与 market_service 的做法**不同**（market_service 内部直接调用 `_broadcast_market_event`），但更符合关注点分离原则。

### 6.2 与 market_service 广播模式的对比

| 维度 | market_service | bounty_service（本次） |
|------|---------------|----------------------|
| 广播位置 | service 内部 | 调用方（autonomy_service） |
| 广播失败影响 | 可能抛异常影响事务 | try/except 吞异常，不影响状态变更 |
| 解耦程度 | 低（service 依赖 chat.broadcast） | 高（service 无 WS 依赖） |

建议：M6.3 统一 market_service 的广播模式，将广播从 service 内部移到调用方，与 bounty_service 对齐。

### 6.3 AC-8 保证

`_broadcast_bounty_event()` 内部 `try/except Exception` 吞异常 + warning log。即使 WebSocket 连接断开或广播超时，bounty 的状态变更（已 flush 到 DB session）不受影响，后续 commit 正常执行。

### 6.4 双广播设计

claim 成功后发出两个事件：
1. `agent_action`（通用行为事件，复用 `_broadcast_action`）— 前端行为日志展示
2. `bounty_claimed`（悬赏专用事件，`_broadcast_bounty_event`）— 前端悬赏面板实时刷新

两个事件独立发送，任一失败不影响另一个。

---

## 7. 风险评估

| # | 风险 | 概率 | 影响 | 缓解措施 |
|---|------|------|------|----------|
| R1 | SYSTEM_PROMPT 变更导致 LLM 决策质量下降（其他行为受干扰） | 低 | 中 | claim_bounty 规则描述简洁明确，ST 回归覆盖全行为类型 |
| R2 | 悬赏振荡：多 Agent 反复尝试 claim 同一悬赏，浪费 tick | 中 | 低 | M6.2 接受（20 Agent 规模可控），M6.3 引入冷却时间 + 竞争概率感知 |
| R3 | tool_call 场景下 handler 自行 commit 但缺少广播 | 低 | 低 | tool_call 是对话场景，前端通过 API 轮询或下次快照感知状态变化，不依赖实时广播 |
| R4 | bounty_service 与 market_service 事务模式不一致（flush vs commit） | 低 | 中 | ADR-2 已记录有意偏离的理由，测试守护 no-self-commit 约束 |
| R5 | SQLite 写锁在高并发下阻塞 | 极低 | 中 | 原型阶段 20 Agent + 低频 claim，锁竞争概率可忽略。生产环境切 PostgreSQL |

---

## 8. 评审结论

### 架构一致性

SR-P3 的设计与现有自主性引擎的"意图-执行分离"架构高度一致。新增的 claim_bounty 行为在快照注入、SYSTEM_PROMPT 引导、白名单校验、执行分支、广播通知五个环节均遵循了 checkin/purchase/construct_building 等已有行为的模式，学习成本低，回归风险小。

### 需关注的偏离

1. bounty_service 的事务策略（只 flush）与 market_service（自行 commit）不一致 — 有意偏离，理由充分（ADR-2），但需在代码注释中明确说明
2. 广播职责放在调用方而非 service 内部 — 比 market_service 更解耦，建议 M6.3 统一

### 建议

1. bounty_service.claim_bounty() 函数头部加注释说明"不自行 commit"的设计意图
2. tool_call handler 中 claim 成功后考虑补发 `_broadcast_bounty_event`（当前 SR 未覆盖，但不影响 M6.2 验收）
3. M6.3 技术债清单追加：market_service 广播模式对齐、complete_bounty 抽取到 bounty_service

### 结论

**通过**。SR-P3 架构设计合理，可进入编码阶段。

# 后端开发进展记录

> 本文件记录后端（server/）的详细开发进展。
> 只有大里程碑完成后才同步到项目总进展 `../claude-progress.txt`。

---

## 当前状态

- **当前任务**: M6.2 补丁包全部完成（P1~P4）
- **最近完成**: M6.2-P4（公共记忆知识库填充）
- **待办优先级**: M6.3（经济重构）
- **阻塞问题**: 无

---

## 进展日志

### 2026-02-22

#### M6.2-P2 完成 — SOUL 深度人格

**改动内容**（15 文件，+646 -21）：

后端：
1. **tables.py**: Agent 表新增 `personality_json` JSON 列
2. **database.py**: `_migrate_personality_json` 迁移函数
3. **schemas.py**: `SoulPersonality` Pydantic 模型（lenient 截断校验）+ AgentOut/AgentCreate/AgentUpdate 扩展
4. **agents.py**: create/update 端点增加 `_validate_personality_json()` 校验清洗
5. **agent_runner.py**: `SOUL_PROMPT_TEMPLATE` + `_build_soul_block()` + `get_or_create` 缓存刷新可变字段
6. **chat.py**: `handle_wakeup` 透传 `personality_json`
7. **autonomy_service.py**: `chat_tasks` 构造新增 `personality_json`

前端：
8. **types.ts**: `SoulPersonality` 接口 + Agent 接口加 `personality_json`
9. **AgentManager.tsx**: AgentCard 只读渲染 SOUL 人格（7 字段）+ relationships 超 3 对换行
10. **App.css**: `.ac-soul` 样式（行间距 4px、word-break）

测试：
11. **test_soul_personality.py**（新建）: 29 UT — schema 校验/清洗逻辑/prompt 格式化/模板分支/缓存刷新
12. **test_soul_e2e.py**（新建）: 7 E2E — 创建/截断/无效忽略/更新/清除/无 SOUL/extra strip

流程落盘：
13. **flow-rules.md**: DEV-4×17 + DEV-39×2
14. **_index.md**: 索引更新
15. **checklist-code-change.md**: 第 11 条门控顺序

**CR 修复**: get_or_create 缓存过期 personality_json → 刷新可变字段（persona/model/personality_json）

**美学审核修复**: 行间距 2→4px、word-break: break-word、relationships 超 3 对换行

**验证**: 283 passed, 11 skipped 全绿

**状态**: ✅ 完成

---

#### M6.2-P3 完成 — 悬赏 Agent 自主接取

**改动内容**：

后端：
1. **bounty_service.py**（新建）: `claim_bounty()` CAS 原子校验，同时最多 1 个悬赏限制
2. **autonomy_service.py**: `build_world_snapshot()` 新增第 11 板块"悬赏任务" + SYSTEM_PROMPT 追加 `claim_bounty` + 白名单 + 执行分支 + 广播函数
3. **tool_registry.py**: `_handle_claim_bounty()` + `CLAIM_BOUNTY_TOOL` 注册
4. **bounties.py**: API 重构为调用 bounty_service

测试：
5. **test_autonomy_unit.py**（新建）: 世界快照/白名单/执行成功失败场景

**状态**: ✅ 完成

---

#### M6.2-P4 完成 — 公共记忆知识库填充

**改动内容**：

1. **main.py**: `seed_public_memories()` 幂等差集 + `begin_nested()` 单条失败跳过
2. **data/public_memories.json**: 10~15 条世界观/规则种子数据

测试：
3. **test_seed_public_memories.py**（新建）: 幂等性/字段正确性/embedding 失败/自愈
4. **test_st_seed_public_memories.py**（新建）: 向量检索可用性/启动不阻塞

**状态**: ✅ 完成

---

**改动内容**：
- `chat.py:_extract_memory()` 重写为 LLM 摘要（fire-and-forget 模式）
- `MODEL_REGISTRY` 新增 `memory-summary-model`
- Fallback 链: openrouter gemma-3-12b → siliconflow qwen2.5-7b → 截断兜底

**验证**: 276 passed 全绿

**状态**: ✅ 完成

---

#### M6 Phase 3 完成 — F35 Agent 状态可视化

**改动内容**：

后端：
1. **tables.py**: AgentStatus 枚举扩展（IDLE/THINKING/EXECUTING/PLANNING），Agent.activity 字段
2. **status_helper.py**（新建）: `set_agent_status()` — 状态变更 + WS 广播 `agent_status_change`
3. **agent_runner.py**: generate_reply 状态生命周期（THINKING→EXECUTING→IDLE）
4. **autonomy_service.py**: tick() 状态生命周期 + rest action 立即恢复 IDLE
5. **schemas.py**: AgentOut 补 activity/satiety/mood/stamina 字段

前端：
6. **AgentStatusPanel.tsx**: 4 态颜色徽章 + 按状态排序
7. **ActivityFeed.tsx**: 10 种 action 标签（含 tool_call/farm_work/mill_work）
8. **DiscordLayout.tsx**: WS 处理 agent_status_change + agent_action 事件，actionLabels 同步
9. **App.css**: mention-status 改用 CSS 变量（--status-online/busy/offline）
10. **types.ts**: Agent.status 5 态 + 注释

测试：
11. **test_agent_status.py**（新建）: 6 个单元测试
12. **e2e_m6_p3.py**（新建）: 4 ST 场景 13 断言

**Code Review**（2 轮独立 CR，P0/P1/P2 全量归零）：
- P1-1: CSS 硬编码颜色 → CSS 变量
- P1-2: DiscordLayout actionLabels 补齐 assign_building/unassign_building/tool_call
- P1-3: rest action 立即恢复 IDLE（不等最终兜底）
- P2-1~4: types.ts 注释、timestamp T 分隔符、ActivityFeed 补 farm_work/mill_work、e2e events 初始化
- P2-5~6（二次 CR）: AgentOut 补 satiety/mood/stamina、agent_runner/autonomy_service timestamp 统一

**验证**: pytest 239/239 全绿 + ST 13/13 全绿

**状态**: ✅ 完成

---

#### M6 Phase 3 SR 确认 — F35 Agent 状态可视化

**文档**：`docs/specs/SPEC-001-核心系统/M6-Agent运行时/SR-M6-Phase3.md`

**三个设计决策（全部拍板）**：
- DC-1：状态枚举 idle/thinking/executing/planning（替换 CHATTING/WORKING/RESTING）
- DC-2：复用 system_event，新增 `agent_status_change` 事件
- DC-3：静态颜色方案（蓝/绿/紫/灰，无脉冲动画）

**范围**：
- 后端：tables.py 枚举替换 + agent_runner.py/autonomy_service.py 状态变更插入 + WS 广播
- 前端：types.ts 5 态 + AgentStatusPanel 排序升级 + DiscordLayout WS 处理 + ActivityFeed tool_call + CSS 颜色
- 测试：test_agent_status.py（7 用例）+ e2e_m6_p3.py（4 ST 场景）

**PM 审核**：通过（DC-3 脉冲动画改为静态蓝色，用户确认）

**F34 长任务编排**：按 IR 评审结论推迟到 M6.3，已完成代码基础设施探索备用。

**状态**: SR 已确认，待编码

---

#### M6 Phase 1 T4 完成 — LLM 策略触发率 100%

**背景**：T4 验证关卡（LLM 输出质量 Go/No-Go），原 10 轮测试策略率 70%。

**根因**：SYSTEM_PROMPT 策略触发规则为建议性文字（"资源明显不足"、"有购买意愿"），模型倾向于选安全的即时行为（checkin）。

**修复**（`autonomy_service.py` SYSTEM_PROMPT）：
- 将策略触发改为三步骤**强制规则**（"必须输出"语言）
- `keep_working`：居民在岗 + 对应资源 < 20 → 必须设策略
- `opportunistic_buy`：扫描市场卖出品种 → 居民对应资源 < 10 且 credits > 0 → 必须设策略

**新增文件**：
- `validate_m6_forced.py`：极端场景单轮强制触发测试（wheat=0、flour=0、超低价单）

**验证**：
- 强制触发测试：✅ 100%（两种策略都触发）
- 10 轮 LLM 质量测试：✅ 100%（10/10 轮有策略，策略总数 19）

---

#### M6 Phase 1 完成 — 策略自动机端到端验证

**改动内容**：

1. **strategy_engine.py**：`clear_strategies` 支持按 agent_id 清空
2. **autonomy_service.py**：`execute_strategies` 预加载资源时补充 `Agent.credits`（修复 opportunistic_buy 支付检查永远失败的 bug）
3. **agents.py**：新增 `POST /api/agents/{id}/strategies`（设置策略）、`DELETE /api/agents/{id}/strategies`（清空策略）
4. **dev_trigger.py**：新增 `POST /api/dev/execute-strategies`（手动触发策略执行，ST 用）
5. **tests/test_m6_e2e.py**（新建）：4 个 pytest 集成测试（keep_working/opportunistic_buy/跳过高价单/观测API）
6. **e2e_m6.py**（新建）：真实服务器 ST 脚本，4 场景 15 个断言

**验证**：pytest 231/231 全绿 + ST 15/15 全绿

---

#### M5.2 交易市场 — Phase 1 + 2 + 2.5 完成

**改动内容**：

1. **tables.py**: AgentResource.frozen_amount + MarketOrder + TradeLog 表
2. **market_service.py** (新建): create_order / accept_order / cancel_order / list_orders / get_trade_logs
3. **city.py**: 5 个 REST 路由 (GET/POST /market/orders, accept, cancel, trade-logs) + Pydantic 校验
4. **tool_registry.py**: 3 个交易市场工具注册 (create_market_order / accept_market_order / cancel_market_order)
5. **前端**: types.ts (MarketOrder/TradeLog) + api.ts (5 个 market 函数) + TradePage.tsx (挂单/接单/撤单 UI) + TradePage.css

**Code Review 修复**（2 轮 review，P0/P1 归零）：
- P0-1: MarketOrder.seller_name 改为可选（后端不返回此字段）
- P1-1: 卖家 label 独占一行（grid 布局修正）
- P1-2: 接单成功后 setAcceptRatio(1.0) 重置
- P1-3: 撤单加 confirm() 确认
- P1-4: CSS 硬编码颜色替换为 CSS 变量 + themes.css 新增 warning/danger

**验证**: 后端 211/211 全绿 + 前端 TS 零错误 + Vite 构建通过 + 13/13 前端测试全绿

**ST 脚本**: e2e_m5_2.py (8 个场景: 挂单/不足/全量接单/部分接单/撤单/非本人撤单/WS广播/成交日志)

**状态**: ✅ 完成（ST 16/16 全绿 + pytest 211/211 全绿）

---

### 2026-02-19

#### M5.1 完成 — 资源转赠 + Tool Use

**改动内容**：

1. **tool_registry.py** (新建): Tool Use 框架，`ToolRegistry` 单例 + `_handle_transfer_resource`
2. **agent_runner.py**: `generate_reply()` 加 tool_call 循环（最多 1 轮），从 tool_registry 获取工具定义
3. **autonomy_service.py**: SYSTEM_PROMPT 新增 `transfer_resource` 动作，`decide()` 校验参数
4. **city_service.py**: `transfer_resource()` 成功后广播 `resource_transferred` 事件

**前端**：TradePage.tsx（交易面板）、React Router、API 包装、类型扩展

**验证**: ST 8/8 全绿（ST-1~4 纯 REST + ST-5 真实 LLM Tool Use）

**状态**: ✅ 完成

---

### 2026-02-17

#### M2 Phase 4 完成 — Batch 推理优化

**改动内容**：

1. **agent_runner.py**: `AgentRunnerManager.batch_generate()` — 按模型分组并发调用 LLM，每个协程独立 AsyncSession
2. **wakeup_service.py**: `scheduled_trigger()` 返回 `list[int]`（多 Agent 唤醒），新增 `SCHEDULED_WAKEUP_PROMPT` + `_resolve_names`
3. **scheduler.py**: 新增 `hourly_wakeup_loop()` — 每小时定时触发 batch 推理 + 错开广播
4. **chat.py**: 新增 `delayed_send()` — 延迟发送 + 经济扣费 + 记忆提取
5. **main.py**: lifespan 启动 hourly wakeup loop
6. **config.py**: Settings 加 `extra="ignore"` 兼容 .env 额外字段

**Code Review 修复**（1 轮 review，目标 ≤2 轮达成）：
- P1-01/P1-05: batch_generate 改为每协程独立 AsyncSession（消除并发共享风险）
- P1-04: 移除 scheduler.py 未使用的 send_agent_message 导入
- P1-08: delayed_send 中 history 防御性拷贝
- P1-10: 新增 3 个 delayed_send 单元测试
- P2-06: 移除未使用的 import random

**验证**: 106/106 测试全绿（92 原有 + 14 新增）

**状态**: ✅ 完成

---

### 2026-02-16

#### M2 Phase 3 完成 — 记忆注入上下文 + 对话提取记忆 + 悬赏API

**改动内容**：

1. **M2-3 记忆注入 Agent 上下文**: `agent_runner.py` generate_reply 新增 db 参数，调用 memory_service.search 检索 top-5 记忆注入 system prompt
2. **M2-4 对话自动提取记忆**: `chat.py` 新增 `_extract_memory`，每 5 条回复触发对话摘要提取为短期记忆
3. **M2-8 悬赏任务 API**: 此前已完成

**附带修复**：
- test_chat_economy.py mock 返回值修正
- upsert_memory 死参数移除
- broadcast 清理逻辑
- print→logger 统一

**验证**: 4 轮 code review 循环，P0/P1 归零，84/84 测试全绿

**状态**: ✅ 完成

---

### 2026-02-14

#### 16:00 - M1 #1 Phase 1 后端实施完成

**改动文件清单**：

1. `app/models/tables.py` — Message 新增 sender_type/message_type/mentions 字段；Agent 新增 daily_free_quota/quota_used_today/quota_reset_date 经济字段
2. `app/api/schemas.py` — 修复 gold→credits；新增 AgentUpdate/WsChatMessage schema；AgentOut 扩展经济字段；MessageOut 扩展 sender_type/message_type/mentions；修复 Pydantic deprecated warnings
3. `app/api/agents.py` — 补全 PUT/DELETE 接口；Agent name 唯一性校验；name 字符集校验（`[\w\u4e00-\u9fff]`）；保护 Human Agent (id=0) 不可修改/删除；列表接口排除 Human Agent
4. `app/api/chat.py` — 扩展 WebSocket 协议（新消息格式 + 向后兼容）；@提及解析（parse_mentions）；系统通知（agent_online/agent_offline）；修复 N+1 查询（JOIN 加载）；sender_type 自动判断；人类消息强制 message_type=work
5. `app/core/config.py` — 修复 Pydantic deprecated warnings
6. `main.py` — 改用 lifespan 替代 deprecated on_event；启动时自动初始化 Human Agent (id=0)

**测试**：
- `tests/test_smoke.py` — 11 个测试全部通过
  - health check、Human Agent 初始化、Agent CRUD（创建/重名/非法名/列表/更新/删除）、Human Agent 保护、消息查询

**状态**: ✅ 完成

---

## 技术债务

- [ ] Agent CRUD 缺少分页功能
- [ ] M2-1 向量搜索降级开关（embedding API 不可用时 fallback 到关键词匹配）

## 遗留问题

- [ ] **M2-1 向量搜索降级开关**: embedding API 不可用时 fallback 到关键词匹配，需在 `vector_store.py` 和 `config.py` 加 `VECTOR_SEARCH_ENABLED` 开关

---

## 大里程碑记录

| 里程碑 | 完成时间 | 验证 |
|--------|----------|------|
| M1 Agent CRUD + WebSocket + 唤醒引擎 + LLM 集成 | 2026-02-14 | 11 冒烟测试 ✅ + E2E ✅ |
| M2 记忆与经济系统（Phase 1-6） | 2026-02-16 | 14/14 E2E 全绿 ✅ |
| M3 城市经济闭环 | 2026-02-17 | E2E ✅ |
| M4 Agent 自主行为 | 2026-02-18 | 9 E2E + 10 单元测试 ✅ |
| M5 记忆系统 + 城市经济 | 2026-02-18 | E2E ✅ |
| M5.1 资源转赠 + Tool Use | 2026-02-19 | ST 8/8 全绿 ✅ |
| M5.2 交易市场（挂单/接单/撤单） | 2026-02-20 | ST 16/16 全绿 + pytest 211/211 ✅ |
| M6.2-P1 记忆提取质量优化 | 2026-02-22 | pytest 276 passed ✅ |
| M6.2-P2 SOUL 深度人格 | 2026-02-22 | 283 passed, 11 skipped ✅ |
| M6.2-P3 悬赏 Agent 自主接取 | 2026-02-22 | UT ✅ |
| M6.2-P4 公共记忆知识库填充 | 2026-02-22 | UT + ST ✅ |

# 后端开发进展记录

> 本文件记录后端（server/）的详细开发进展。
> 只有大里程碑完成后才同步到项目总进展 `../claude-progress.txt`。

---

## 当前状态

- **当前任务**: M2 Phase 4 完成，进入验收
- **最近完成**: M2 Phase 4（Batch 推理优化）
- **待办优先级**: 无阻塞项，可进入下一阶段
- **阻塞问题**: 无

---

## 进展日志

### 2026-02-16 (续)

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

## 待办事项

- [ ] M1 #2 唤醒/意图识别规则引擎（wakeup_service.py）
- [ ] M1 #3 模拟消息触发器（测试用）
- [ ] M1 #5 LLM 集成（agent_runner.py）
- [ ] WebSocket 集成测试（多连接广播、@提及、系统通知）

---

## 技术债务

- [ ] Agent CRUD 缺少分页功能
- [ ] WebSocket 断线重连 / 心跳机制
- [ ] GET /api/messages 增加 since_id 增量拉取（Phase 2）
- [ ] agent_typing 系统事件（Phase 2）

## 遗留问题

- [ ] **M2-1 向量搜索降级开关**: 如果 embedding API 不可用（key 未配置/网络不通），记忆检索应 fallback 到关键词匹配，不走向量搜索。配置缺失时启动报 warning。需要在 `vector_store.py` 和 `config.py` 加开关字段（如 `VECTOR_SEARCH_ENABLED=true`）。

---

## 遇到的问题及解决

详见 [错题本](../docs/runbooks/error-books/error-book-dev.md)（#1 lifespan 不触发、#2 端口冲突、#3 Windows curl 编码）

---

## 大里程碑记录

### M1.1 - Agent CRUD + WebSocket 基础功能
- **完成时间**: 2026-02-14
- **包含内容**: Agent CRUD API（含 PUT/DELETE）+ WebSocket 聊天协议升级 + 消息持久化 + Human Agent 初始化
- **验证标准**: 11 个冒烟测试通过 ✅ + 前后端联调通过 ✅ + Playwright 黑盒测试通过 ✅
- **同步状态**: ✅ 联调完成

### M1.2 - 唤醒引擎 + Agent 回复引擎
- **完成时间**: 2026-02-14
- **包含内容**: WakeupService（@必唤 + 小模型选人 + 定时触发）+ AgentRunner（LLM 调用 + 增量上下文）+ chat.py 异步唤醒集成
- **验证标准**: 代码就绪，需配置 OpenRouter API key 后端到端验证
- **同步状态**: ⏳ 待 LLM 调用验证

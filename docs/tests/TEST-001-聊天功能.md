# TEST-001: Agent 聊天功能 测试用例文档

**关联设计**: TDD-001-聊天功能
**关联需求**: REQ-001-聊天功能
**编写角色**: QA Lead
**编写日期**: 2026-02-14

---

## 测试范围

按 TDD-001 三阶段划分测试范围：

| Phase | 功能 | 测试类型 |
|-------|------|----------|
| Phase 1 | WebSocket 通信、消息持久化、@提及解析、Human Agent | 单元 + 集成 |
| Phase 2 | 唤醒服务、AgentRunner、小模型选人 | 单元 + 集成 |
| Phase 3 | 经济服务、额度控制、信用点扣减 | 单元 + 集成 |
| 全链路 | 用户发消息 → Agent 自动回复 | 端到端 |

---

## Phase 1 测试用例：基础聊天

### UT-1.1 @提及解析 (parse_mentions)

| 用例 ID | 输入 | 期望输出 | 说明 |
|---------|------|----------|------|
| UT-1.1.1 | `"@Alice 你好"`, `{"Alice": 1}` | `[1]` | 正常单人@提及 |
| UT-1.1.2 | `"@Alice 你好 @Bob 你也来"`, `{"Alice": 1, "Bob": 2}` | `[1, 2]` | 多人@提及 |
| UT-1.1.3 | `"大家好"`, `{"Alice": 1}` | `[]` | 无@提及 |
| UT-1.1.4 | `"@Unknown 你好"`, `{"Alice": 1}` | `[]` | @不存在的 Agent |
| UT-1.1.5 | `"@小明 你好"`, `{"小明": 3}` | `[3]` | 中文名@提及 |
| UT-1.1.6 | `"@@Alice 你好"`, `{"Alice": 1}` | `[1]` | 连续@符号 |
| UT-1.1.7 | `""`, `{"Alice": 1}` | `[]` | 空消息 |
| UT-1.1.8 | `"email@test.com"`, `{"test": 5}` | `[]` 或 `[5]` | 邮箱格式误匹配（需确认行为） |
| UT-1.1.9 | `"@Alice@Bob"`, `{"Alice": 1, "Bob": 2}` | `[1]` 或 `[1, 2]` | 连续@无空格（需确认行为） |

> 注：UT-1.1.8 和 UT-1.1.9 是边界场景，实施时需确认预期行为并补充断言。

### UT-1.2 Agent Name 校验

| 用例 ID | 输入 | 期望结果 | 说明 |
|---------|------|----------|------|
| UT-1.2.1 | `"Alice"` | 通过 | 纯英文 |
| UT-1.2.2 | `"小明"` | 通过 | 纯中文 |
| UT-1.2.3 | `"Agent_01"` | 通过 | 下划线+数字 |
| UT-1.2.4 | `"Dr. Smith"` | 拒绝 | 含空格和点号 |
| UT-1.2.5 | `"Alice!!"` | 拒绝 | 含特殊字符 |
| UT-1.2.6 | `""` | 拒绝 | 空名字 |
| UT-1.2.7 | `"A" * 65` | 拒绝 | 超过 64 字符限制 |

### IT-1.1 WebSocket 连接与消息广播

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-1.1.1 | 客户端 A 连接 `/ws/1`，发送 `{"type": "chat_message", "content": "hello"}` | 客户端 A 收到广播消息，包含 id、agent_id=1、agent_name、content="hello"、created_at |
| IT-1.1.2 | 客户端 A 和 B 同时在线，A 发消息 | A 和 B 都收到广播 |
| IT-1.1.3 | 客户端 A 发送旧格式 `{"content": "hello"}` | 服务端正常处理（向后兼容），广播包含完整字段 |
| IT-1.1.4 | 客户端 A 断开连接 | connections 中移除 A，后续广播不发给 A |
| IT-1.1.5 | 客户端 A 断开后重连 | 重连成功，能正常收发消息 |

### IT-1.2 消息持久化

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-1.2.1 | 发送一条消息 | GET /api/messages 返回该消息，包含 sender_type、message_type、mentions 字段 |
| IT-1.2.2 | 发送带@提及的消息 `"@Alice 你好"` | 持久化的 mentions 字段为 `[alice_id]` |
| IT-1.2.3 | 发送 50+ 条消息，GET /api/messages?limit=10 | 只返回最近 10 条，按时间正序 |

### IT-1.3 Human Agent

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-1.3.1 | 服务启动 | 数据库中存在 id=0 的 Human Agent |
| IT-1.3.2 | 客户端连接 `/ws/0` 发消息 | sender_type="human"，message_type="work" |
| IT-1.3.3 | Human 发送 `{"type": "chat_message", "message_type": "chat"}` | 服务端强制覆盖为 message_type="work" |

### IT-1.4 系统通知

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-1.4.1 | Agent 连接 WebSocket | 所有在线客户端收到 `{"type": "system_event", "data": {"event": "agent_online", ...}}` |
| IT-1.4.2 | Agent 断开 WebSocket | 所有在线客户端收到 `{"type": "system_event", "data": {"event": "agent_offline", ...}}` |

---

## Phase 2 测试用例：Agent 自动回复

### UT-2.1 WakeupService 唤醒决策

| 用例 ID | 输入场景 | 期望 wake_list | 说明 |
|---------|----------|----------------|------|
| UT-2.1.1 | 消息含 `@Alice`（id=1） | `[1]` | @必唤 |
| UT-2.1.2 | 消息含 `@Alice @Bob` | `[1, 2]` | 多人@必唤 |
| UT-2.1.3 | 人类消息，无@，小模型返回 "Bob" | `[bob_id]` | 人类消息选人 |
| UT-2.1.4 | 人类消息 `@Alice`，小模型选 Bob | `[1, bob_id]` | @必唤 + 选人叠加 |
| UT-2.1.5 | 人类消息 `@Alice`，小模型也选 Alice | `[1]` | 去重，Alice 只回复一次 |
| UT-2.1.6 | Agent 消息，无@，小模型返回 "NONE" | `[]` | 无人需要回复 |
| UT-2.1.7 | Agent 消息，无@，小模型返回 "Alice" | `[1]` | Agent 间接话触发 |
| UT-2.1.8 | Agent A 发消息，小模型选中 A 自己 | `[]` | 不能自己回复自己 |

### UT-2.2 AgentRunner 上下文管理

| 用例 ID | 场景 | 期望结果 |
|---------|------|----------|
| UT-2.2.1 | 新 Agent 首次回复 | 从数据库加载最近消息作为上下文 |
| UT-2.2.2 | 热 Agent 连续回复 5 次 | 内存上下文包含这 5 轮 |
| UT-2.2.3 | 热 Agent 上下文达到 20 轮后再收到消息 | FIFO 裁剪，移除最旧的 1 轮，保持 20 轮 |
| UT-2.2.4 | AgentRunnerManager.get_runner(不存在的 id) | 创建新实例（冷启动） |

### IT-2.1 唤醒 → 回复完整链路

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-2.1.1 | Human 发消息（无@） | 小模型选人 → 被选 Agent 生成回复 → 回复广播给所有连接 |
| IT-2.1.2 | Human 发 `@Alice 你好` | Alice 必定回复 + 可能另一个 Agent 也回复 |
| IT-2.1.3 | Agent A 发消息 | 小模型判断 → 可能无人回复（概率较低触发） |
| IT-2.1.4 | OpenRouter 超时/失败 | fallback 到规则引擎随机选人，不报错 |

### IT-2.2 定时触发

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-2.2.1 | 有活跃非 Agent 连接，定时触发 | 小模型判断是否有 Agent 主动发言 |
| IT-2.2.2 | 无活跃连接，定时触发 | 跳过，不触发任何 Agent |
| IT-2.2.3 | 只有 Agent 连接（无人类），定时触发 | 跳过（串讲补充项：至少 1 个非 Agent 连接） |

---

## Phase 3 测试用例：经济约束

### UT-3.1 EconomyService 额度检查与扣减

| 用例 ID | 场景 | 期望结果 | 说明 |
|---------|------|----------|------|
| UT-3.1.1 | Agent 闲聊，quota_used=0，free_quota=10 | `(True, "free_quota")`，quota_used → 1 | 免费额度内 |
| UT-3.1.2 | Agent 闲聊，quota_used=9，free_quota=10 | `(True, "free_quota")`，quota_used → 10 | 免费额度最后一次 |
| UT-3.1.3 | Agent 闲聊，quota_used=10，credits=5 | `(True, "credit_deducted")`，credits → 4 | 超出免费额度，扣信用点 |
| UT-3.1.4 | Agent 闲聊，quota_used=10，credits=1 | `(True, "credit_deducted")`，credits → 0 | 信用点最后一个 |
| UT-3.1.5 | Agent 闲聊，quota_used=10，credits=0 | `(False, "insufficient_credits")` | 信用点不足，拒绝 |
| UT-3.1.6 | Agent 工作发言 | `(True, "work_free")`，不扣任何资源 | 工作免费 |
| UT-3.1.7 | Agent 闲聊，quota_reset_date 是昨天 | 先重置 quota_used → 0，再正常检查 | 跨天重置 |
| UT-3.1.8 | Agent 闲聊，quota_reset_date 是今天 | 不重置，正常检查 | 同天不重置 |

### UT-3.2 经济预检查（选人阶段，只读）

| 用例 ID | 场景 | 期望结果 |
|---------|------|----------|
| UT-3.2.1 | Agent 有额度 | 可被选为回复者 |
| UT-3.2.2 | Agent 无额度无信用点 | 不被选为回复者 |
| UT-3.2.3 | 预检查后 Agent 未实际回复 | 额度不变（只读，未扣减） |

### IT-3.1 经济约束集成

| 用例 ID | 步骤 | 期望结果 |
|---------|------|----------|
| IT-3.1.1 | Agent 连续闲聊 11 次（free_quota=10） | 前 10 次扣免费额度，第 11 次扣信用点 |
| IT-3.1.2 | Agent 信用点耗尽后被@提及 | @必唤但经济检查拒绝，返回错误通知 |
| IT-3.1.3 | 跨天后 Agent 再次闲聊 | 额度已重置，使用免费额度 |

---

## 端到端测试用例

### E2E-1 完整聊天链路

| 用例 ID | 场景 | 步骤 | 期望结果 |
|---------|------|------|----------|
| E2E-1.1 | 人类发消息触发 Agent 回复 | 1. Human 连接 /ws/0<br>2. 发送 "大家好"<br>3. 等待 Agent 回复 | 消息广播 → Agent 回复出现在聊天室 |
| E2E-1.2 | @提及触发回复 | 1. Human 发送 "@Alice 你觉得呢？"<br>2. 等待 Alice 回复 | Alice 必定回复，内容与人格一致 |
| E2E-1.3 | 多人@提及 | 1. Human 发送 "@Alice @Bob 讨论一下"<br>2. 等待回复 | Alice 和 Bob 都回复 |
| E2E-1.4 | 额度耗尽场景 | 1. Agent 闲聊 10 次（耗尽免费额度）<br>2. 继续闲聊<br>3. 信用点耗尽后再闲聊 | 第 11 次扣信用点，信用点耗尽后拒绝 |
| E2E-1.5 | 断线重连 | 1. 客户端连接并收到消息<br>2. 断开连接<br>3. 重连<br>4. GET /api/messages 补拉 | 重连后能看到断线期间的消息 |

---

## 测试环境要求

- 后端：FastAPI 测试客户端（httpx + pytest-asyncio）
- WebSocket 测试：`websockets` 库或 FastAPI TestClient
- 小模型 Mock：WakeupService 的 OpenRouter 调用需 mock，避免依赖外部 API
- LLM Mock：AgentRunner 的 LLM 调用需 mock，返回固定回复
- 数据库：每个测试用例使用独立的 SQLite 内存数据库（`:memory:`）

---

## 测试优先级

| 优先级 | 用例范围 | 原因 |
|--------|----------|------|
| P0 | UT-1.1（@解析）、IT-1.1（WebSocket 广播）、IT-1.2（持久化） | Phase 1 核心功能，阻塞后续所有开发 |
| P1 | UT-3.1（经济检查）、UT-2.1（唤醒决策）、IT-1.3（Human Agent） | 核心业务逻辑 |
| P2 | IT-2.1（唤醒链路）、IT-3.1（经济集成）、E2E 全部 | 集成验证 |
| P3 | UT-1.2（Name 校验）、IT-1.4（系统通知）、IT-2.2（定时触发） | 辅助功能 |

---

## 审核记录

- [x] QA Lead 完成初稿（2026-02-14）
- [x] Developer 确认可测试性（2026-02-14）
- [ ] Architect 确认覆盖率

---

**编写日期**：2026-02-14
**编写角色**：QA Lead
**基于设计**：TDD-001-聊天功能
**串讲补充项**：已纳入（Agent name 校验、定时触发前置条件、经济两步检查）

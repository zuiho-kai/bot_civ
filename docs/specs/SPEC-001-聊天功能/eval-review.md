# SPEC-001 四方评审记录

**日期**: 2026-02-14
**参与者**: Architect、Tech Lead、QA Lead、Developer

---

## 架构视角（Architect）

**架构符合性**: ✅ 基本符合

**风险**:
1. ⚠️ WebSocket 连接管理是单进程内存 Dict — 单点瓶颈，多实例部署广播失效
2. ⚠️ chat.py 中 N+1 查询问题 — 50条消息产生50次额外查询
3. ⚠️ 缺少唤醒/意图识别层 — 需要 WakeupService
4. ⚠️ 缺少发言频率/额度控制中间件

**建议**: 短期修复 N+1 + 断线重连；中期在 services/ 设计 ChatOrchestrator 抽象

---

## 技术视角（Tech Lead）

**技术可行性**: ✅ 完全可行

**技术难点**:
1. WebSocket 连接管理（后续需 Redis Pub/Sub）
2. Agent 唤醒/意图识别集成（异步 LLM 调用）
3. 发言频率控制与经济系统联动（事务一致性）
4. 前端 WebSocket 状态管理（断线重连、乐观更新）
5. @提及解析与路由

**技术风险**:
1. OpenRouter 免费模型稳定性（需降级策略）
2. SQLite 并发写入（启用 WAL）
3. 内存泄漏（WebSocket 异常断开清理，需心跳）
4. LLM 调用延迟（广播不应阻塞，异步解耦）
5. sentence-transformers 内存占用（~500MB-1GB）

**建议**: 优先完成纯聊天（无 LLM 唤醒），再逐步叠加

---

## 测试视角（QA Lead）

**可测试性**: ⚠️ 中等

**测试难点**:
1. 小模型选人的非确定性（需 mock）
2. WebSocket 并发与广播时序
3. 额度与经济系统耦合（边界条件多）
4. @提及解析与唤醒链（终止条件）
5. 人类 vs Agent 发言区分

**关键测试场景（10个）**:

正常流程:
1. Agent WebSocket 发消息 → 所有在线 Agent 收到广播
2. @提及 → 必定唤醒并回复
3. 人类发言 → 小模型选人回复（工作发言不消耗额度）
4. GET /api/messages 返回正确历史消息

异常流程:
5. 断线重连 → 不丢失断线期间消息
6. 空消息/超长消息/非法JSON → 拒绝并返回错误
7. 不存在的 agent_id 连接 → 拒绝连接

边界条件:
8. 闲聊额度耗尽后@Agent → 判断信用点
9. 同一 Agent 被多人同时@提及 → 合并处理
10. 0个 Agent 在线时发消息 → 持久化但无广播

**额外风险**:
1. 同一 agent_id 重复连接会覆盖前一个
2. Message 表需 sender_type 字段
3. 需先实现 mentions 字段和@解析

---

## 实施视角（Developer）

**实施复杂度**: 中

**后端 ~400-600 行新增/修改**:
- chat.py 大幅扩展
- 新建 wakeup_service.py (~150行)、economy_service.py (~80行)、agent_runner.py (~120行)
- schemas.py 新增消息类型
- tables.py 新增字段

**前端 ~800-1200 行新增**:
- ChatRoom / MessageList / MessageBubble / ChatInput / AgentSidebar
- useWebSocket hook / api.ts / 状态管理 / 样式

---

## 需求澄清决策

| # | 问题 | 决策 |
|---|------|------|
| 1 | 人类用户身份 | Human Agent (id=0, name="Human") |
| 2 | Agent 自动回复架构 | 方案G（OpenClaw SDK + 150行封装）→ [辩论详情](讨论细节/Agent架构方案.md) |
| 3 | 数据库字段补充 | 新增 sender_type + mentions |
| 4 | 消息类型扩展 | 第一版支持系统通知（上线/离线） |
| 5 | 前端 UI 设计稿 | Developer 自由发挥，参考 Discord/Slack |

---

## Go/No-Go: ✅ Go

批准进入设计阶段。技术可行、架构健康、风险可控、工作量合理。

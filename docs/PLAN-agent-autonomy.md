# Agent 自主性改造实施方案（M4）

**目标**: 让 Agent 从"提线木偶"变成"自主公民" — 自己决定打卡/购买/聊天/休息

**核心洞察**: 时间表模式无法模拟突发事件的连锁反应（大雨→农作物失收→Alice 破产→Bob 恐慌抛售→价格暴跌→Carol 抄底）。只有"每轮基于实时世界状态决策"才能产生二阶以上的涌现效应。

**原则**: 最小改动，复用现有基础设施（work_service / shop_service / agent_runner / broadcast 全部保留）

---

## 方案：世界状态驱动的单次 LLM 决策

### 核心架构

每小时一次，把整个世界快照塞进一次 LLM 调用，让 LLM 以"城市模拟器"视角为所有 Agent 做出行为决策。

```
每小时触发（autonomy_loop）
  ↓
构建世界状态快照（~20k token）
  ├─ 每个 Agent: persona摘要 + credits + 今日打卡 + 持有物品
  ├─ 最近 10 条聊天 + 上一轮行为日志
  └─ 岗位列表（含空位）+ 商品列表（含价格）
  ↓
单次 LLM 调用（城市模拟器 prompt）
  → 输出 JSON：每个 Agent 的 action + params + reason
  ↓
串行执行决策
  ├─ checkin → work_service.check_in()
  ├─ purchase → shop_service.purchase()
  ├─ chat → 收集起来，走 batch_generate 生成内容
  └─ rest → 跳过
  ↓
广播事件 + 动态 Feed
```

### 为什么聊天生成要独立推理

决策阶段（谁做什么）和聊天生成（怎么说）解决不同问题：
- 决策用"上帝视角"全局分配，一次调用够
- 聊天需要独立 persona + 私人记忆 + 语气一致性，否则会"人格污染"
- 现有 `batch_generate` 已验证有效，每个 Agent 独立调用保证人格独立

### 成本估算

- 决策调用：24 次/天（每小时 1 次）
- 聊天生成：~72 次/天（平均每轮 3 个 Agent 选择 chat）
- 总计：~96 次/天（免费额度 10%）
- 模型：复用 MODEL_REGISTRY 中已有模型（Arcee Trinity / StepFun）
- 世界状态构建：~50ms（6 个 DB 查询）

---

## 文件变更清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `server/app/services/autonomy_service.py` | 世界状态构建 + LLM 决策 + 解析 + 执行（~250行） |
| 修改 | `server/app/services/scheduler.py` | 新增 autonomy_loop（~30行） |
| 修改 | `server/main.py` | lifespan 启动 autonomy_loop（~5行） |
| 新建 | `web/src/components/ActivityFeed.tsx` | 实时动态 feed 组件（~60行） |
| 修改 | `web/src/components/InfoPanel.tsx` | 替换 AnnouncementPanel → ActivityFeed |
| 修改 | `web/src/components/DiscordLayout.tsx` | 收集 activity 事件 |
| 修改 | `web/src/components/MessageBubble.tsx` | 支持 agent_action 系统消息渲染 |
| 修改 | `web/src/types.ts` | 新增 Activity 类型 |

## 不改动的部分

- `agent_runner.py` — 复用 batch_generate，不改
- `wakeup_service.py` — 保留现有聊天唤醒逻辑，不改
- `economy_service.py` — 复用，不改
- `work_service.py` / `shop_service.py` — 复用，不改
- `chat.py` — 仅复用 broadcast 和 send_agent_message，不改核心逻辑
- 数据库 schema — 不加新表，不改现有表

## 实施顺序

1. IR（需求原型）→ 用户确认
2. SR（需求拆分）→ 用户确认
3. AR（技术设计）→ 用户确认
4. 编码 + Code Review
5. 端到端验证

# TDD-M4 — Agent 自主行为

> 对应 IR：`01-需求原型.md` §M4（US-M4-1 ~ US-M4-5, F11 ~ F13）
> 对应 SR：`02-需求拆分.md` §M4（M4-1 ~ M4-7）

---

## 1. 架构概览

```
scheduler.py                    autonomy_service.py
┌──────────────┐    tick()     ┌─────────────────────────────┐
│autonomy_loop │──────────────▶│ build_world_snapshot(db)     │
│ 每小时+抖动  │               │ decide(snapshot) → LLM 调用  │
└──────────────┘               │ execute_decisions(decs, db)  │
                               └──────┬──────────────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                  ▼
             work_service       shop_service      runner_manager
             .check_in()        .purchase()       .batch_generate()
                    │                 │                  │
                    └─────────────────┼──────────────────┘
                                      ▼
                              WebSocket broadcast
                              (system_event: agent_action)
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                                    ▼
              ActivityFeed                        MessageBubble
              (InfoPanel 替换 mock)               (聊天区系统消息)
```

核心思路：每小时一次，构建世界状态快照 → 单次 LLM 调用（城市模拟器视角）→ 解析决策 JSON → 逐条执行 → 广播事件。

---

## 2. 数据流

```
1. autonomy_loop 触发 tick()
2. build_world_snapshot(db):
   - SELECT agents (id != 0): persona摘要, credits, 今日打卡, 持有物品
   - SELECT 最近 10 条聊天记录
   - 读取上一轮行为日志（内存缓存）
   - SELECT 岗位列表(含空位) + 商品列表(含价格)
   - 拼装结构化文本 (~20k token 以内)
3. decide(snapshot):
   - 构建 system prompt（城市模拟器角色）
   - 注入 snapshot 到 user message
   - 调用 LLM (resolve_model + AsyncOpenAI)
   - 解析返回 JSON 数组
   - 每条: {"agent_id": int, "action": str, "params": dict, "reason": str}
4. execute_decisions(decisions, db):
   - checkin → work_service.check_in(agent_id, db)
   - purchase → shop_service.purchase(agent_id, item_id, db)
   - chat → 收集列表, 最后 batch_generate + send_agent_message
   - rest → 跳过
   - 每条广播 system_event(event="agent_action", ...)
5. 前端接收 system_event → ActivityFeed 追加 + 聊天区轻量提示
```

---

## 3. 文件清单

### 新建文件

| 文件 | 职责 |
|------|------|
| `server/services/autonomy_service.py` | 世界状态构建 + LLM 决策 + 决策执行 |
| `web/src/components/ActivityFeed.tsx` | 动态 Feed 组件 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `server/scheduler.py` | 新增 `autonomy_loop()` |
| `server/main.py` | lifespan 中 `create_task(autonomy_loop())` |
| `web/src/components/InfoPanel.tsx` | 替换 mock AnnouncementPanel → ActivityFeed |
| `web/src/components/MessageBubble.tsx` | 扩展 system_event 渲染，支持 agent_action |

---

## 4. 接口定义

### 4.1 autonomy_service.py

```python
# server/services/autonomy_service.py

from server.database import get_db
from server.services.work_service import WorkService
from server.services.shop_service import ShopService
from server.services.economy_service import EconomyService
from server.agent_runner import RunnerManager
from server.chat import broadcast, send_agent_message
from server.config import resolve_model
import json, logging, asyncio

logger = logging.getLogger(__name__)

# 上一轮行为日志（内存缓存，重启丢失可接受）
_last_round_log: list[dict] = []


async def build_world_snapshot(db) -> str:
    """构建世界状态快照，返回结构化文本。

    包含：
    - 所有非人类 Agent 的 persona 摘要、credits、今日打卡状态、持有物品
    - 最近 10 条聊天记录
    - 上一轮行为日志
    - 岗位列表（含当日空位）+ 商品列表（含价格）

    控制在 ~20k token 以内。
    """
    ...


async def decide(snapshot: str) -> list[dict]:
    """调用 LLM 做出行为决策。

    system prompt: 城市模拟器角色
    user message: 世界状态快照
    返回: [{"agent_id": int, "action": str, "params": dict, "reason": str}, ...]
    action 枚举: "checkin" | "purchase" | "chat" | "rest"

    容错: JSON 解析失败 → 记录日志，返回空列表
    """
    ...


async def execute_decisions(decisions: list[dict], db) -> dict:
    """逐条执行决策。

    返回: {"success": int, "failed": int, "skipped": int}

    执行逻辑:
    - checkin → work_service.check_in(agent_id, db)
    - purchase → shop_service.purchase(agent_id, params["item_id"], db)
    - chat → 收集到 chat_tasks 列表
    - rest → skipped += 1
    - 聊天统一走 batch_generate + send_agent_message
    - 每个动作独立 try/except，单个失败不影响其他
    - 成功后广播 system_event(event="agent_action", agent_id, action, reason)
    """
    ...


async def tick(db=None):
    """一次完整的自主行为循环。

    1. build_world_snapshot
    2. decide
    3. execute_decisions
    4. 更新 _last_round_log
    """
    ...
```

### 4.2 scheduler.py 新增

```python
async def autonomy_loop():
    """Agent 自主行为定时循环。

    - 启动后等 60s（让系统初始化完成）
    - 每小时触发一次 autonomy_service.tick()
    - 加 0-120s 随机抖动，避免与 hourly_wakeup_loop 完全同步
    - 异常不退出循环，记录日志后继续
    """
    await asyncio.sleep(60)
    while True:
        jitter = random.randint(0, 120)
        await asyncio.sleep(jitter)
        try:
            async with get_db_session() as db:
                await autonomy_service.tick(db)
        except Exception as e:
            logger.error(f"autonomy_loop 异常: {e}")
        await asyncio.sleep(3600 - jitter)
```

### 4.3 WebSocket 事件格式

```json
{
  "type": "system_event",
  "data": {
    "event": "agent_action",
    "agent_id": 3,
    "agent_name": "Alice",
    "action": "checkin",
    "reason": "早上到了，该去矿场上班了",
    "timestamp": "2026-02-18 09:15:00+00:00"
  }
}
```

### 4.4 ActivityFeed.tsx

```tsx
// web/src/components/ActivityFeed.tsx

interface ActivityItem {
  agent_id: number;
  agent_name: string;
  action: "checkin" | "purchase" | "chat" | "rest";
  reason: string;
  timestamp: string;
}

// 监听 WebSocket system_event (event === "agent_action")
// 最多保留最近 50 条，FIFO 淘汰
// 每条显示：Agent 名字 + 行为描述 + 理由 + 相对时间
```

### 4.5 聊天区系统消息增强

在 MessageBubble 中扩展 system_event 渲染：

```tsx
// event === "agent_action" 时的轻量展示
// 示例："Alice 在「矿工」岗位打卡了"
// 示例："Bob 购买了「面包」"
// 复用现有 system_event 渲染逻辑，扩展 event 类型映射
```

---

## 5. LLM Prompt 设计

### System Prompt（城市模拟器）

```
你是一个虚拟城市的模拟器。你的任务是根据当前世界状态，为每个居民决定下一步行为。

规则：
1. 每个居民只能选择一个行为：checkin（打卡上班）、purchase（购买商品）、chat（发言聊天）、rest（休息）
2. 行为必须合理：
   - 已打卡的不能重复打卡
   - 余额不足的不能购买
   - 行为应符合居民的性格特征
3. 不是所有人每小时都要行动，rest 是合理选择
4. 聊天内容不需要你生成，只需决定谁要聊天

输出格式：JSON 数组，每个元素：
{"agent_id": <int>, "action": "<checkin|purchase|chat|rest>", "params": {}, "reason": "<一句话理由>"}

params 说明：
- checkin: {} （岗位由系统自动匹配）
- purchase: {"item_id": <int>}
- chat: {} （聊天内容由专门的聊天系统生成）
- rest: {}
```

### User Message

```
当前时间：{current_time}

== 居民状态 ==
{agent_summaries}

== 最近聊天 ==
{recent_messages}

== 上一轮行为 ==
{last_round_log}

== 可用岗位 ==
{job_listings}

== 商店商品 ==
{shop_items}

请为每个居民决定下一步行为。
```

---

## 6. 容错与边界

| 场景 | 处理 |
|------|------|
| LLM 返回非法 JSON | 记录日志，本轮跳过，不崩溃 |
| LLM 返回未知 action | 当作 rest 处理 |
| agent_id 不存在 | 跳过该条决策 |
| check_in 失败（已打卡） | 记录日志，继续下一条 |
| purchase 失败（余额不足/商品不存在） | 记录日志，继续下一条 |
| chat 经济预检查失败 | 跳过该 agent 的聊天 |
| LLM 调用超时/网络错误 | 记录日志，本轮跳过 |
| autonomy_loop 异常 | 记录日志，不退出循环，下一小时重试 |

---

## 7. 测试计划

### 单元测试

| 测试 | 覆盖 |
|------|------|
| `test_build_world_snapshot` | 快照包含所有必要字段，token 估算 ≤ 20k |
| `test_decide_valid_json` | mock LLM 返回有效 JSON，解析正确 |
| `test_decide_invalid_json` | mock LLM 返回乱码，返回空列表不崩溃 |
| `test_execute_checkin` | mock work_service，验证调用 + 广播 |
| `test_execute_purchase` | mock shop_service，验证调用 + 广播 |
| `test_execute_chat` | mock batch_generate，验证收集 + 批量调用 |
| `test_execute_rest` | 验证跳过，skipped 计数 |
| `test_execute_failure_isolation` | 一条失败不影响后续执行 |

### 集成测试（ST）

| 场景 | 验证 |
|------|------|
| 启动服务等待 autonomy_loop 触发 | Agent 产生自主行为 |
| checkin/purchase/chat/rest 四种决策 | 各自正确执行 |
| 已打卡 / 余额不足 | 静默跳过 |
| LLM 返回异常 | 不崩溃 |
| 前端 ActivityFeed | 实时显示动态 |
| 连续 3 轮 | 不同 Agent 行为有差异（人格体现） |

---

## 8. 开发顺序

```
Phase 1: M4-1 世界状态构建 → M4-2 LLM 决策 → M4-3 决策执行 → M4-4 定时循环
Phase 2: M4-5 ActivityFeed + M4-6 聊天区增强（可并行）
Phase 3: M4-7 端到端验证
```

Phase 1 完成后跑后端 ST，Phase 2 完成后跑全链路 ST。

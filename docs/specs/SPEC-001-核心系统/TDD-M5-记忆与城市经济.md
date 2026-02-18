# TDD-M5 — 记忆系统 + 城市经济

> 对应 IR：`01-需求原型.md` §M5（US-M5-1 ~ US-M5-15, F14 ~ F20, AC-M5-01 ~ AC-M5-24）
> 对应 SR：`02-需求拆分.md` §M5（M5-1 ~ M5-11）

## 范围裁剪

| 内容 | M5 | M5.1 | M6 |
|------|:--:|:----:|:--:|
| 官府田（唯一建筑，max_workers=2，产 flour） | ✅ | | |
| flour 资源 | ✅ | | |
| 饮食（吃 flour 恢复三维属性） | ✅ | | |
| 每日属性结算（饱腹度/心情/体力） | ✅ | | |
| stamina 字段 + 体力机制 | ✅ | | |
| autonomy 扩展（assign/unassign/eat） | ✅ | | |
| 记忆管理面板（独立 tab，CRUD + 统计） | ✅ | | |
| 城市面板（建筑/工人/属性/资源） | ✅ | | |
| 转赠资源（transfer） | | ✅ | |
| 农田、磨坊、wheat 资源 | | | ✅ |
| 交易市场（挂单/接单/撤单） | | | ✅ |
| MarketOrder / TradeLog 表 | | | ✅ |

---

## 1. 架构概览

```
scheduler.py                    city_service.py
┌──────────────────┐            ┌─────────────────────────────────┐
│daily_city_tick   │──────────▶│ daily_attribute_decay(db)        │
│ 每日 00:00       │            │ daily_production(db)             │
└──────────────────┘            └─────────────────────────────────┘

autonomy_service.py (扩展)
┌──────────────────┐  tick()   ┌─────────────────────────────────┐
│autonomy_loop     │─────────▶│ build_world_snapshot(db) [扩展]   │
│ 每小时+抖动      │           │ decide(snapshot) [扩展 prompt]    │
└──────────────────┘           │ execute_decisions(decs, db)[扩展] │
                               └──────┬──────────────────────────┘
                                      │ 新增动作
                    ┌────────┬────────┼────────┐
                    ▼        ▼        ▼        ▼
              city_service  city_service  city_service
              .assign_worker .unassign   .eat_food
                    │        │        │
                    └────────┴────────┘
                             ▼
                     WebSocket broadcast
                     (system_event 扩展)
                             │
                    ┌────────┴────────┐
                    ▼                 ▼
              CityPanel         MemoryAdmin
              (建筑/资源/属性)  (记忆 CRUD，独立 tab)
```

核心思路：
- 每日定时：属性结算 → 生产结算（串行，属性先于生产）
- 每小时 autonomy_loop：扩展世界快照 + 新增 3 种决策动作（assign_building / unassign_building / eat）
- 记忆管理：独立模块，与城市经济无依赖

---

## 2. 数据模型变更

### 2.1 Agent 表新增字段

```python
# server/app/models/tables.py — Agent 类新增
stamina = Column(Integer, default=100)  # 体力 0-100
```

现有字段：satiety（饱腹度）、mood（心情）已存在，无需改动。

迁移函数：`migrate_add_stamina()` — ALTER TABLE agents ADD COLUMN stamina INTEGER DEFAULT 100

### 2.2 已有表（无需改动，仅确认实际字段）

- Building（id, name, building_type, city, owner, max_workers, description, created_at）
  - 注意：生产逻辑按 building_type 硬编码（"farm"→wheat, "mill"→wheat→flour），M5 新增 "gov_farm" 类型
- BuildingWorker（id, building_id, agent_id, assigned_at）— 唯一约束 (building_id, agent_id)
  - ⚠️ 当前约束允许一个 Agent 同时在多个建筑工作，M5 需在 assign_worker 中加检查：Agent 已在任何建筑则拒绝
- Resource（id, city, resource_type, quantity）— 城市公共资源池，M5 不使用
- AgentResource（id, agent_id, resource_type, quantity）— Agent 个人资源，无 frozen_amount
- ProductionLog（id, building_id, agent_id, input_type, input_qty, output_type, output_qty, tick_time）

### 2.3 资源类型命名

现有代码使用 "flour" 而非 "wheat_flour"。M5 沿用现有命名：
- `flour` = 面粉（小麦粉）
- `wheat` = 小麦（M6 才用）

### 2.4 seed 数据

| 类型 | 数据 | 说明 |
|------|------|------|
| Building | 官府田 x1（building_type="gov_farm", max_workers=2） | 虚空造币，无需原料，直接产出 flour |

注意：
- 不需要 seed Resource 表（公共资源池），官府田产出直接进工人个人背包（AgentResource）
- wheat、农田、磨坊均不在 M5 seed 中，留 M6
- 现有 seed 中如有农田/磨坊，M5 不删除但不影响（production_tick 按 building_type 分支处理）

---

## 3. 数值设计

### 3.1 饮食恢复值

| 食物 | 消耗量 | 饱腹度恢复 | 心情恢复 | 体力恢复 |
|------|--------|-----------|---------|---------|
| flour | 1 | +30 | +10 | +20 |

所有属性上限 100，恢复后 min(当前值 + 恢复值, 100)。

现有 eat_food 已实现 flour -1 / satiety +30 / mood +10，M5 扩展加 stamina +20。

### 3.2 每日属性结算

| 属性 | 每日变化 | 条件 |
|------|---------|------|
| 饱腹度 | -15 | 无条件 |
| 体力 | +15 | 无条件（自然恢复） |
| 心情 | -10 | 饱腹度 < 30 时 |
| 心情 | -20 | 饱腹度 = 0 时 |
| 心情 | 不变 | 饱腹度 >= 30 时 |

注意：现有 production_tick 已包含饱腹度/心情衰减（satiety -15, mood 按饱腹度分档）。M5 将属性结算拆为独立函数 daily_attribute_decay()，从 production_tick 中移出，并新增 stamina 恢复逻辑。

所有属性下限 0，上限 100。

### 3.3 工作消耗

| 动作 | 体力消耗 |
|------|---------|
| 生产（每日结算） | -15 |

体力阈值：< 20 时无法工作（生产结算跳过该 Agent）。

---

## 4. 接口定义

### 4.1 city_service.py 扩展

现有接口保持不变，新增/修改：

```python
# 新增：每日属性结算（从 production_tick 中拆出）
async def daily_attribute_decay(db: AsyncSession):
    """每日属性结算。
    遍历所有非人类 Agent：
    - satiety -= 15（下限 0）
    - stamina += 15（上限 100）
    - mood: 饱腹度=0 时 -20，饱腹度<30 时 -10，否则不变（下限 0）
    注意：现有 production_tick 中的衰减逻辑移到这里，production_tick 不再做属性衰减。
    """

# 修改：assign_worker 增加跨建筑检查
# 现有 assign_worker(city, building_id, agent_id, db) 签名不变
# 新增校验：Agent 已在任何建筑工作 → 返回 {"ok": False, "reason": "已在其他建筑工作，请先离职"}

# 复用现有 remove_worker 作为离职接口
# 现有签名：remove_worker(city, building_id, agent_id, db)
# autonomy 调用时需先查 Agent 当前在哪个建筑，再调 remove_worker

# 修改：eat_food 增加 stamina 恢复
# 现有签名不变：eat_food(agent_id, db)
# 扩展：stamina = min(100, stamina + 20)
# 返回值扩展：{"ok": True, "reason": "吃饱了", "satiety": int, "mood": int, "stamina": int}

# 修改：production_tick 增加体力检查和消耗 + 官府田分支
# 现有 production_tick(city, db) 签名不变
# 新增 building_type == "gov_farm" 分支：无原料直接产出 flour
# 工人 stamina < 20 → 跳过，记录日志
# 生产成功后 stamina -= 15（下限 0）
# 移除属性衰减逻辑（已拆到 daily_attribute_decay）
```

### 4.2 memory_admin_service.py 扩展

确认现有接口，补充缺失的：

```python
async def list_memories(agent_id: int | None, memory_type: str | None,
                        keyword: str | None, page: int, size: int,
                        db: AsyncSession) -> dict:
    """列表 + 筛选 + 搜索 + 分页。
    返回：{"items": [...], "total": int, "page": int, "size": int}
    """

async def get_memory_detail(memory_id: int, db: AsyncSession) -> dict | None:
    """记忆详情。"""

async def create_memory(agent_id: int, memory_type: str, content: str,
                        db: AsyncSession) -> dict:
    """手动创建记忆。"""

async def update_memory(memory_id: int, content: str,
                        db: AsyncSession) -> dict:
    """编辑记忆内容。"""

async def delete_memory(memory_id: int, db: AsyncSession) -> dict:
    """删除记忆。"""

async def get_memory_stats(agent_id: int | None,
                           db: AsyncSession) -> dict:
    """统计：数量、类型分布。"""
```

### 4.3 autonomy_service.py 扩展

```python
# build_world_snapshot 扩展内容：
# 在现有快照基础上新增：
# - 每个 Agent 的三维属性（satiety, mood, stamina）
# - 每个 Agent 的个人资源背包（AgentResource）
# - 建筑工人分配（BuildingWorker）+ 各建筑空位数
# - 每个 Agent 的当前在岗状态（在哪个建筑 / 无业）

# decide() prompt 扩展：
# action 枚举新增：assign_building, unassign_building, eat
# params 说明：
#   assign_building: {"building_id": <int>}
#   unassign_building: {}
#   eat: {}
# 体力 < 20 的 Agent 标注 "[体力不足，无法工作]"
# 已在岗的 Agent 标注 "[在岗：{建筑名}]"

# execute_decisions() 扩展：
# 新增 action 处理分支：
#   assign_building → city_service.assign_worker(city, building_id, agent_id, db)
#   unassign_building → 先查 BuildingWorker 找到 building_id，再调 city_service.remove_worker(city, building_id, agent_id, db)
#   eat → city_service.eat_food(agent_id, db)
```

### 4.4 REST API

#### 记忆管理 API（确认/补充 server/app/api/memory.py）

```
GET    /api/memories             — 列表（?agent_id=&type=&keyword=&page=1&size=20）
GET    /api/memories/{id}        — 详情
POST   /api/memories             — 创建（body: {agent_id, memory_type, content}）
PUT    /api/memories/{id}        — 编辑（body: {content}）
DELETE /api/memories/{id}        — 删除
GET    /api/memories/stats       — 统计（?agent_id=）
```

#### 城市 API（扩展 server/app/api/city.py）

现有路由已覆盖大部分需求，仅需补充：

```
GET  /api/agents/{id}/attributes       — 查询 Agent 三维属性（新增）
  返回: {satiety, mood, stamina}
```

已有路由（无需改动）：
- `GET /cities/{city}/overview` — 城市概览（扩展返回值加 agent 属性）
- `GET /cities/{city}/buildings` — 建筑列表
- `GET /cities/{city}/buildings/{id}` — 建筑详情
- `POST /cities/{city}/buildings/{id}/workers` — 应聘（assign_worker）
- `DELETE /cities/{city}/buildings/{id}/workers/{aid}` — 离职（remove_worker）
- `POST /agents/{agent_id}/eat` — 吃饭
- `GET /agents/{agent_id}/resources` — 个人资源

### 4.5 WebSocket 事件格式

```json
// 生产结算
{
  "type": "system_event",
  "data": {
    "event": "production_settled",
    "agent_id": 3,
    "agent_name": "Alice",
    "building_name": "官府田",
    "resource": "flour",
    "amount": 5,
    "timestamp": "2026-02-18 00:00:00+00:00"
  }
}

// 属性变化
{
  "type": "system_event",
  "data": {
    "event": "attribute_changed",
    "agent_id": 3,
    "agent_name": "Alice",
    "satiety": 80,
    "mood": 75,
    "stamina": 85,
    "timestamp": "2026-02-18 00:00:00+00:00"
  }
}

// 饮食
{
  "type": "system_event",
  "data": {
    "event": "agent_ate",
    "agent_id": 3,
    "agent_name": "Alice",
    "resource": "flour",
    "amount": 1,
    "timestamp": "2026-02-18 12:00:00+00:00"
  }
}

// 应聘上岗
{
  "type": "system_event",
  "data": {
    "event": "worker_assigned",
    "agent_id": 3,
    "agent_name": "Alice",
    "building_name": "官府田",
    "timestamp": "2026-02-18 10:00:00+00:00"
  }
}

// 离职
{
  "type": "system_event",
  "data": {
    "event": "worker_unassigned",
    "agent_id": 3,
    "agent_name": "Alice",
    "building_name": "官府田",
    "timestamp": "2026-02-18 14:00:00+00:00"
  }
}
```

---

## 5. LLM Prompt 扩展

### System Prompt 追加规则

```
5. 新增行为：
   - assign_building（应聘上岗）：选择一个有空位的建筑工作，一个 Agent 同时只能在一个建筑
   - unassign_building（离职）：离开当前建筑，腾出岗位
   - eat（吃饭）：消耗个人面粉，恢复饱腹度/心情/体力
6. 体力不足（标注 [体力不足]）的居民不能选择 assign_building
7. 饱腹度低的居民应优先考虑 eat
8. 已在岗的居民不能重复 assign_building，需先 unassign_building 再换岗

params 说明（追加）：
- assign_building: {"building_id": <int>}
- unassign_building: {}
- eat: {}
```

### User Message 追加段落

```
== 居民属性 ==
{agent_attributes}
（每个 Agent: 饱腹度/心情/体力，体力<20 标注 [体力不足，无法工作]）

== 个人资源 ==
{agent_resources}
（每个 Agent 的背包资源列表）

== 建筑与工人 ==
{building_workers}
（每个建筑的工人分配情况 + 空位数，已在岗 Agent 标注 [在岗：建筑名]）
```

---

## 6. 文件清单

### 新建文件

| 文件 | 职责 |
|------|------|
| `web/src/components/CityPanel.tsx` | 城市经济面板（建筑/工人/属性/资源） |
| `web/src/components/MemoryAdmin.tsx` | 记忆管理面板（独立 tab，CRUD + 统计） |

### 修改文件

| 文件 | 改动 |
|------|------|
| `server/app/models/tables.py` | Agent 新增 stamina 字段 |
| `server/app/core/database.py` | 迁移函数 migrate_add_stamina |
| `server/app/services/city_service.py` | 新增 daily_attribute_decay() + unassign_worker()，production_tick 增加体力检查/消耗 |
| `server/app/services/autonomy_service.py` | 扩展快照/prompt/决策执行（3 种新动作） |
| `server/app/services/scheduler.py` | 新增 daily_city_tick（属性结算 + 生产结算） |
| `server/app/services/memory_admin_service.py` | 补充 list/detail/create/update/delete/stats 接口 |
| `server/app/api/memory.py` | 补充 REST 路由 |
| `server/app/api/city.py` | 新增属性查询 + 城市概览 + 离职 API |
| `web/src/components/InfoPanel.tsx` | 新增 Tab 入口（城市 + 记忆） |
| `web/src/components/ActivityFeed.tsx` | 扩展支持新事件类型（production_settled / attribute_changed / agent_ate / worker_assigned / worker_unassigned） |

---

## 7. 容错与边界

| 场景 | 处理 |
|------|------|
| 吃饭无面粉 | 返回 {ok: false, reason: "面粉不足"} |
| 体力不足时生产 | 跳过该工人，记录日志 |
| 属性溢出 | min/max 钳制到 0-100 |
| 应聘满员建筑 | 返回 {ok: false, reason: "建筑已满员"} |
| 已在岗时再次应聘 | 返回 {ok: false, reason: "已在其他建筑工作，请先离职"} |
| 未在岗时离职 | 返回 {ok: false, reason: "未在任何建筑工作"} |
| autonomy 新动作执行失败 | 记录日志，继续下一条决策 |
| LLM 返回未知新动作 | 当作 rest 处理（与 M4 一致） |

---

## 8. 测试计划

### 单元测试

| 测试 | 覆盖 |
|------|------|
| `test_daily_attribute_decay` | 饱腹度下降、体力恢复、心情按饱腹度分档下降 |
| `test_attribute_clamp` | 属性不超 100、不低于 0 |
| `test_production_stamina_check` | 体力 < 20 跳过，>= 20 正常生产并消耗体力 |
| `test_production_guanfutian` | 官府田无原料直接产出 flour |
| `test_eat_food` | 扣 flour、恢复三维属性（含 stamina） |
| `test_eat_food_insufficient` | 无 flour 时失败 |
| `test_assign_worker` | 应聘成功，BuildingWorker 创建 |
| `test_assign_worker_full` | 满员时应聘失败 |
| `test_assign_worker_already_employed` | 已在岗时应聘失败 |
| `test_unassign_worker` | 离职成功，BuildingWorker 删除 |
| `test_unassign_worker_not_employed` | 未在岗时离职失败 |
| `test_memory_crud` | 创建/读取/更新/删除记忆 |
| `test_memory_list_filter` | 按 agent/type/keyword 筛选 |
| `test_memory_stats` | 统计数量和类型分布 |
| `test_world_snapshot_extended` | 快照包含属性/资源/建筑工人/空位数 |
| `test_execute_new_actions` | assign_building/unassign_building/eat 正确调用 |

### 集成测试（E2E）

| 场景 | 验证 |
|------|------|
| 官府田生产 | 在岗工人背包 flour 增加（虚空造币） |
| 吃饭成功 | flour 减少，三维属性恢复（含 stamina） |
| 吃饭失败 | 无 flour 时返回错误 |
| 每日属性结算 | 饱腹度下降、体力恢复、心情按条件变化 |
| 体力不足生产 | 该 Agent 被跳过，不产出 |
| 应聘上岗 | BuildingWorker 创建，WS 推送 worker_assigned |
| 应聘满员 | 返回错误 |
| 离职 | BuildingWorker 删除，WS 推送 worker_unassigned |
| autonomy 选建筑 | LLM 决策 assign_building，BuildingWorker 更新 |
| autonomy 吃饭 | LLM 决策 eat，属性恢复 |
| 记忆 CRUD | 创建/编辑/删除/筛选均正常 |
| 记忆统计 | 数量和类型分布正确 |
| 城市面板 | 建筑/工人/属性/资源正确展示 |
| 记忆面板 | 独立 tab，CRUD 操作正常 |
| WS 推送 | 所有新事件类型正确广播 |

---

## 9. 开发顺序

```
Phase 1: 数据模型迁移（Agent.stamina）+ seed 确认（官府田 building_type="gov_farm"）
Phase 2: city_service 扩展（daily_attribute_decay + unassign_worker + production_tick 体力检查）+ memory_admin_service 补全（并行）
Phase 3: autonomy_loop 集成（扩展快照/prompt/执行，3 种新动作）
Phase 4: 前端面板（CityPanel + MemoryAdmin 独立 tab）+ WS 新事件 + REST API 补全（并行）
Phase 5: 端到端验证
```

Phase 1 完成后跑迁移验证。Phase 2 完成后跑后端 UT。Phase 3 完成后跑 autonomy UT。Phase 4-5 跑全链路 E2E。

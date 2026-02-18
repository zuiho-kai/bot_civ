# TEST-M5: 记忆与城市经济 测试用例文档

**关联设计**: TDD-M5-记忆与城市经济
**关联需求**: 01-需求原型.md §M5
**编写角色**: QA Lead
**编写日期**: 2026-02-18

---

## 测试范围

按 TDD-M5 模块划分测试范围：

| 层级 | 功能 | 测试类型 | 用例数 |
|------|------|----------|--------|
| UT | daily_attribute_decay + production_tick gov_farm + eat_food 三维 + assign_worker 跨建筑 + memory CRUD | 单元测试 | 16 |
| E2E | 官府田闭环 + 吃饭恢复 + 每日结算 + 体力不足 + 满员竞争 + 完整生命周期 + 记忆 CRUD + autonomy 新动作 | 端到端测试 | 8 |

---

## UT 层：单元测试（16 个用例）

### U1: daily_attribute_decay 正常衰减

- **覆盖**: daily_attribute_decay 基本逻辑
- **优先级**: P0
- **Given**: Agent(id=1, satiety=80, stamina=50, mood=60) 存在
- **When**: 调用 `daily_attribute_decay(agent_id=1, db)`
- **Then**:
  - Agent.satiety 变为 65（80-15）
  - Agent.stamina 变为 65（50+15）
  - Agent.mood 不变，仍为 60（satiety>=30，mood 不衰减）
- **测试数据**: Agent(satiety=80, stamina=50, mood=60)

### U2: daily_attribute_decay 饱腹度低

- **覆盖**: daily_attribute_decay 低饱腹度 mood 衰减
- **优先级**: P0
- **Given**: Agent(id=1, satiety=20, stamina=50, mood=60) 存在
- **When**: 调用 `daily_attribute_decay(agent_id=1, db)`
- **Then**:
  - Agent.satiety 变为 5（20-15）
  - Agent.stamina 变为 65（50+15）
  - Agent.mood 变为 50（60-10，因 satiety 衰减后=5 < 30）
- **测试数据**: Agent(satiety=20, stamina=50, mood=60)

### U3: daily_attribute_decay 饱腹度为零

- **覆盖**: daily_attribute_decay 零饱腹度 mood 大幅衰减
- **优先级**: P0
- **Given**: Agent(id=1, satiety=0, stamina=50, mood=60) 存在
- **When**: 调用 `daily_attribute_decay(agent_id=1, db)`
- **Then**:
  - Agent.satiety 仍为 0（0-15 钳制到 0）
  - Agent.stamina 变为 65（50+15）
  - Agent.mood 变为 40（60-20，因 satiety=0）
- **测试数据**: Agent(satiety=0, stamina=50, mood=60)

### U4: daily_attribute_decay 属性钳制

- **覆盖**: daily_attribute_decay 上下限钳制 [0, 100]
- **优先级**: P1
- **Given**: Agent(id=1, satiety=10, stamina=95, mood=30) 存在
- **When**: 调用 `daily_attribute_decay(agent_id=1, db)`
- **Then**:
  - Agent.satiety 变为 0（10-15 钳制到 0，不会变为 -5）
  - Agent.stamina 变为 100（95+15 钳制到 100，不会变为 110）
  - Agent.mood 变为 10（30-20，因 satiety 钳制后=0）
- **测试数据**: Agent(satiety=10, stamina=95, mood=30)

### U5: production_tick gov_farm 正常生产

- **覆盖**: gov_farm 建筑类型生产逻辑
- **优先级**: P0
- **Given**: City(id=1) 存在；Building(id=1, building_type="gov_farm", max_workers=3) 属于 City(id=1)；Agent(id=1, stamina=50) 存在；BuildingWorker(building_id=1, agent_id=1) 存在；Agent(id=1) 的 flour 资源初始为 0
- **When**: 调用 `production_tick(city_id=1, db)`
- **Then**:
  - Agent(id=1) 的 flour 资源增加 5（gov_farm 每 worker 每 tick 产 5 flour）
  - Agent(id=1).stamina 变为 35（50-15）
  - ProductionLog 表新增一条记录（building_id=1, agent_id=1, output="flour", amount=5）
- **测试数据**: City, Building(type="gov_farm"), Agent(stamina=50), BuildingWorker, Resource(flour=0)

### U6: production_tick gov_farm 体力不足跳过

- **覆盖**: gov_farm 体力不足跳过生产
- **优先级**: P0
- **Given**: City(id=1) 存在；Building(id=1, building_type="gov_farm") 属于 City(id=1)；Agent(id=1, stamina=15) 存在；BuildingWorker(building_id=1, agent_id=1) 存在；Agent(id=1) 的 flour 资源初始为 0
- **When**: 调用 `production_tick(city_id=1, db)`
- **Then**:
  - Agent(id=1) 的 flour 资源仍为 0（stamina=15 < 20，跳过生产）
  - Agent(id=1).stamina 仍为 15（未参与生产，不扣体力）
  - 无 ProductionLog 记录生成
- **测试数据**: City, Building(type="gov_farm"), Agent(stamina=15), BuildingWorker, Resource(flour=0)

### U7: production_tick farm 不受影响

- **覆盖**: 已有 farm 逻辑不被 M5 改动破坏
- **优先级**: P1
- **Given**: City(id=1) 存在；Building(id=1, building_type="farm") 属于 City(id=1)；Agent(id=1, stamina=50) 存在；BuildingWorker(building_id=1, agent_id=1) 存在
- **When**: 调用 `production_tick(city_id=1, db)`
- **Then**:
  - City(id=1) 的 wheat 资源增加 10（farm 每 worker 产 10 wheat，逻辑不变）
  - Agent(id=1).stamina 变为 35（50-15，farm 也消耗体力）
- **测试数据**: City, Building(type="farm"), Agent(stamina=50), BuildingWorker

### U8: production_tick 不再做属性衰减

- **覆盖**: production_tick 属性衰减已移至 daily_attribute_decay
- **优先级**: P1
- **Given**: City(id=1) 存在；Agent(id=1, satiety=80, mood=60, stamina=50) 存在；City 无任何建筑（无生产发生）
- **When**: 调用 `production_tick(city_id=1, db)`
- **Then**:
  - Agent(id=1).satiety 仍为 80（production_tick 不再做衰减）
  - Agent(id=1).mood 仍为 60（production_tick 不再做衰减）
- **测试数据**: City(无建筑), Agent(satiety=80, mood=60, stamina=50)

### U9: eat_food 恢复三维属性

- **覆盖**: eat_food 新增 stamina 恢复
- **优先级**: P0
- **Given**: Agent(id=1, satiety=50, mood=60, stamina=40) 存在；Agent(id=1) 的 flour 资源为 3
- **When**: 调用 `eat_food(agent_id=1, db)`
- **Then**:
  - 返回 `{"ok": True, "reason": "success", "satiety": 80, "mood": 70, "stamina": 60}`
  - Agent(id=1).satiety 变为 80（50+30）
  - Agent(id=1).mood 变为 70（60+10）
  - Agent(id=1).stamina 变为 60（40+20）
  - Agent(id=1) 的 flour 资源变为 2（3-1）
- **测试数据**: Agent(satiety=50, mood=60, stamina=40), Resource(flour=3)

### U10: eat_food 无面粉失败

- **覆盖**: eat_food 无面粉拒绝
- **优先级**: P0
- **Given**: Agent(id=1, satiety=50, mood=60, stamina=40) 存在；Agent(id=1) 的 flour 资源为 0
- **When**: 调用 `eat_food(agent_id=1, db)`
- **Then**:
  - 返回 `{"ok": False, "reason": "no_flour"}`
  - Agent(id=1).satiety 仍为 50
  - Agent(id=1).mood 仍为 60
  - Agent(id=1).stamina 仍为 40
- **测试数据**: Agent(satiety=50, mood=60, stamina=40), Resource(flour=0)

### U11: eat_food 属性上限钳制

- **覆盖**: eat_food 属性不超过 100
- **优先级**: P1
- **Given**: Agent(id=1, satiety=90, mood=95, stamina=90) 存在；Agent(id=1) 的 flour 资源为 1
- **When**: 调用 `eat_food(agent_id=1, db)`
- **Then**:
  - Agent(id=1).satiety 变为 100（90+30 钳制到 100，不会变为 120）
  - Agent(id=1).mood 变为 100（95+10 钳制到 100，不会变为 105）
  - Agent(id=1).stamina 变为 100（90+20 钳制到 100，不会变为 110）
  - flour 资源变为 0
- **测试数据**: Agent(satiety=90, mood=95, stamina=90), Resource(flour=1)

### U12: assign_worker 跨建筑检查

- **覆盖**: assign_worker 新增跨建筑重复检查
- **优先级**: P0
- **Given**: Building(id=1, building_type="gov_farm") 和 Building(id=2, building_type="farm") 存在；Agent(id=1) 已在 Building(id=1) 工作（BuildingWorker 记录存在）
- **When**: 调用 `assign_worker(city, building_id=2, agent_id=1, db)`
- **Then**:
  - 返回失败，reason 包含 "已在其他建筑工作，请先离职"
  - BuildingWorker 表无 (building_id=2, agent_id=1) 记录
- **测试数据**: 2 个 Building, Agent(id=1), BuildingWorker(building_id=1, agent_id=1)

### U13: assign_worker 正常应聘

- **覆盖**: assign_worker 无冲突正常分配
- **优先级**: P0
- **Given**: Building(id=1, building_type="gov_farm", max_workers=3) 存在；Agent(id=1) 未在任何建筑工作（无 BuildingWorker 记录）
- **When**: 调用 `assign_worker(city, building_id=1, agent_id=1, db)`
- **Then**:
  - 返回成功
  - BuildingWorker 表新增 (building_id=1, agent_id=1) 记录
- **测试数据**: Building(type="gov_farm", max_workers=3), Agent(id=1), 无 BuildingWorker

### U14: assign_worker 满员拒绝

- **覆盖**: assign_worker 建筑满员拒绝
- **优先级**: P0
- **Given**: Building(id=1, max_workers=2) 存在；Agent(id=3, id=4) 已在 Building(id=1) 工作（2 条 BuildingWorker 记录）；Agent(id=5) 未在任何建筑工作
- **When**: 调用 `assign_worker(city, building_id=1, agent_id=5, db)`
- **Then**:
  - 返回失败，reason 包含满员相关信息
  - BuildingWorker 表无 (building_id=1, agent_id=5) 记录
- **测试数据**: Building(max_workers=2), 2 条已有 BuildingWorker, Agent(id=5)

### U15: memory CRUD

- **覆盖**: memory_admin_service 新增 create/update/delete
- **优先级**: P0
- **Given**: Agent(id=1) 存在；数据库中无该 Agent 的记忆记录
- **When**:
  1. 调用 `create_memory(agent_id=1, content="今天在官府田工作很累", memory_type="experience", db)` → 获得 memory_id
  2. 调用 `get_memory_detail(memory_id, db)` → 查看详情
  3. 调用 `update_memory(memory_id, content="今天在官府田工作很累但很充实", db)` → 更新内容
  4. 调用 `get_memory_detail(memory_id, db)` → 确认更新
  5. 调用 `delete_memory(memory_id, db)` → 删除
  6. 调用 `get_memory_detail(memory_id, db)` → 确认已删除
- **Then**:
  - 步骤 1 返回有效 memory_id
  - 步骤 2 返回 content="今天在官府田工作很累"
  - 步骤 4 返回 content="今天在官府田工作很累但很充实"
  - 步骤 6 返回 None 或抛出 not_found
- **测试数据**: Agent(id=1), 无初始记忆数据

### U16: memory list with keyword filter

- **覆盖**: list_memories 关键词过滤
- **优先级**: P1
- **Given**: Agent(id=1) 存在；已创建 3 条记忆：content 分别为 "在官府田种地", "去磨坊磨面粉", "在官府田吃饭"
- **When**: 调用 `list_memories(agent_id=1, keyword="官府田", db)`
- **Then**:
  - 返回列表长度为 2（仅包含含 "官府田" 的记忆）
  - 不包含 "去磨坊磨面粉" 这条记忆
- **测试数据**: Agent(id=1), 3 条记忆记录

---

## E2E 层：端到端测试（8 个用例）

> 测试方式：拉起真实 FastAPI 服务器，通过 HTTP 客户端调用真实 API，检查真实数据库。

### E1: 官府田完整生产闭环

- **覆盖**: gov_farm 建筑分配→生产→资源产出完整链路
- **优先级**: P0
- **Given**: 服务器已启动；City(id=1) 存在；Building(id=1, building_type="gov_farm", max_workers=3) 属于 City(id=1)；Agent(id=1, stamina=50) 存在；Agent(id=1) 的 flour 资源初始为 0
- **When**:
  1. `POST /api/city/1/buildings/1/assign` body=`{"agent_id": 1}` — 分配工人
  2. `POST /api/city/1/production-tick` — 触发生产
  3. `GET /api/agents/1` — 查询 Agent 属性和资源
- **Then**:
  - 步骤 1 返回成功
  - 步骤 2 返回成功
  - 步骤 3 返回的 Agent 数据中 flour 资源 = 5，stamina = 35（50-15）
- **测试数据**: City, Building(type="gov_farm"), Agent(stamina=50)

### E2: 吃饭恢复属性

- **覆盖**: eat_food 三维属性恢复完整链路
- **优先级**: P0
- **Given**: 服务器已启动；Agent(id=1, satiety=50, mood=60, stamina=40) 存在；Agent(id=1) 的 flour 资源为 2
- **When**:
  1. `GET /api/agents/1` — 记录初始属性
  2. `POST /api/agents/1/eat` — 吃饭
  3. `GET /api/agents/1` — 查询最新属性
- **Then**:
  - 步骤 2 返回 `{"ok": true, "satiety": 80, "mood": 70, "stamina": 60}`
  - 步骤 3 返回的 Agent 数据中 satiety=80, mood=70, stamina=60, flour=1
- **测试数据**: Agent(satiety=50, mood=60, stamina=40), Resource(flour=2)

### E3: 每日属性结算

- **覆盖**: daily_attribute_decay 独立结算链路
- **优先级**: P0
- **Given**: 服务器已启动；Agent(id=1, satiety=80, mood=60, stamina=50) 存在
- **When**:
  1. `GET /api/agents/1` — 记录初始属性
  2. `POST /api/city/1/daily-decay` — 触发每日属性结算
  3. `GET /api/agents/1` — 查询最新属性
- **Then**:
  - 步骤 3 返回的 Agent 数据中 satiety=65（80-15）, stamina=65（50+15）, mood=60（不变，satiety>=30）
- **测试数据**: Agent(satiety=80, mood=60, stamina=50)

### E4: 体力不足无法生产

- **覆盖**: 低体力跳过生产保护机制
- **优先级**: P0
- **Given**: 服务器已启动；City(id=1) 存在；Building(id=1, building_type="gov_farm") 属于 City(id=1)；Agent(id=1, stamina=10) 已分配到 Building(id=1)；Agent(id=1) 的 flour 资源初始为 0
- **When**:
  1. `POST /api/city/1/production-tick` — 触发生产
  2. `GET /api/agents/1` — 查询 Agent 属性和资源
- **Then**:
  - 步骤 2 返回的 Agent 数据中 flour 资源仍为 0（stamina=10 < 20，未生产）
  - Agent.stamina 仍为 10（未参与生产，不扣体力）
- **测试数据**: City, Building(type="gov_farm"), Agent(stamina=10), BuildingWorker 已存在

### E5: 应聘满员竞争

- **覆盖**: 多 Agent 竞争有限岗位
- **优先级**: P1
- **Given**: 服务器已启动；Building(id=1, building_type="gov_farm", max_workers=2) 存在；Agent(id=1), Agent(id=2), Agent(id=3) 均未在任何建筑工作
- **When**:
  1. `POST /api/city/1/buildings/1/assign` body=`{"agent_id": 1}` — 第 1 人应聘
  2. `POST /api/city/1/buildings/1/assign` body=`{"agent_id": 2}` — 第 2 人应聘
  3. `POST /api/city/1/buildings/1/assign` body=`{"agent_id": 3}` — 第 3 人应聘
- **Then**:
  - 步骤 1 返回成功
  - 步骤 2 返回成功
  - 步骤 3 返回失败（满员拒绝）
  - Building(id=1) 的工人数为 2
- **测试数据**: Building(max_workers=2), 3 个 Agent

### E6: 应聘→生产→吃饭→离职 完整生命周期

- **覆盖**: Agent 工作生命周期完整闭环
- **优先级**: P0
- **Given**: 服务器已启动；City(id=1) 存在；Building(id=1, building_type="gov_farm") 属于 City(id=1)；Agent(id=1, satiety=50, mood=60, stamina=50) 存在；Agent(id=1) 的 flour 资源初始为 0
- **When**:
  1. `POST /api/city/1/buildings/1/assign` body=`{"agent_id": 1}` — 应聘
  2. `POST /api/city/1/production-tick` — 生产（获得 5 flour，stamina 50→35）
  3. `POST /api/agents/1/eat` — 吃饭（消耗 1 flour，satiety+30, mood+10, stamina+20）
  4. `POST /api/city/1/buildings/1/remove` body=`{"agent_id": 1}` — 离职
  5. `GET /api/agents/1` — 查询最终状态
- **Then**:
  - 步骤 1 返回成功
  - 步骤 2 返回成功
  - 步骤 3 返回 `{"ok": true, "satiety": 80, "mood": 70, "stamina": 55}`（stamina: 50→35→55）
  - 步骤 4 返回成功
  - 步骤 5 返回的 Agent 数据中 satiety=80, mood=70, stamina=55, flour=4（5-1）
  - Agent 不再属于任何建筑
- **测试数据**: City, Building(type="gov_farm"), Agent(satiety=50, mood=60, stamina=50)

### E7: 记忆 CRUD 完整流程

- **覆盖**: memory_admin_service 完整 CRUD 链路
- **优先级**: P0
- **Given**: 服务器已启动；Agent(id=1) 存在
- **When**:
  1. `POST /api/memory/create` body=`{"agent_id": 1, "content": "今天在官府田工作", "memory_type": "experience"}` — 创建记忆
  2. `GET /api/memory/agents/1/memories` — 列出记忆，确认包含新记忆
  3. `PUT /api/memory/{memory_id}` body=`{"content": "今天在官府田工作，收获了5份面粉"}` — 更新记忆
  4. `GET /api/memory/{memory_id}` — 获取详情，确认已更新
  5. `DELETE /api/memory/{memory_id}` — 删除记忆
  6. `GET /api/memory/agents/1/memories` — 列出记忆，确认已删除
- **Then**:
  - 步骤 1 返回成功，包含 memory_id
  - 步骤 2 返回列表中包含 content="今天在官府田工作" 的记忆
  - 步骤 3 返回成功
  - 步骤 4 返回 content="今天在官府田工作，收获了5份面粉"
  - 步骤 5 返回成功
  - 步骤 6 返回列表中不再包含该 memory_id
- **测试数据**: Agent(id=1)

### E8: autonomy 新动作执行

- **覆盖**: autonomy_service 新增 assign_building/eat 动作
- **优先级**: P1
- **Given**: 服务器已启动；Agent(id=1, satiety=30, stamina=50) 存在；Building(id=1, building_type="gov_farm") 存在；Agent(id=1) 的 flour 资源为 2；LLM mock 配置为依次返回 `assign_building(building_id=1)` 和 `eat` 决策
- **When**:
  1. 触发 autonomy 决策循环（Agent(id=1) 的自主行为 tick）
  2. 等待第一个决策执行完毕（assign_building）
  3. 触发第二轮 autonomy 决策循环
  4. 等待第二个决策执行完毕（eat）
  5. `GET /api/agents/1` — 查询最终状态
- **Then**:
  - 步骤 2 后 Agent(id=1) 已分配到 Building(id=1)（BuildingWorker 记录存在）
  - 步骤 4 后 Agent(id=1) 的 flour 资源减少 1（2→1）
  - 步骤 5 返回的 Agent 数据中 satiety=60（30+30）, mood 增加 10, stamina=70（50+20）
- **测试数据**: Agent(satiety=30, stamina=50), Building(type="gov_farm"), Resource(flour=2), LLM mock

---

## 测试环境要求

- 后端：FastAPI 测试客户端（httpx + pytest-asyncio）
- 数据库：每个测试用例使用独立的 SQLite 内存数据库（`:memory:`）
- E2E 测试：拉起真实 FastAPI 服务器进程，使用 httpx 客户端
- LLM mock：E8 使用 mock LLM 返回预设决策，不调用真实 LLM
- Agent 表需包含 M5 新增的 stamina 字段（Integer, default=100）

---

## 测试优先级

| 优先级 | 用例范围 | 原因 |
|--------|----------|------|
| P0 | U1(正常衰减), U2(低饱腹度), U3(零饱腹度), U5(gov_farm生产), U6(体力不足跳过), U9(吃饭三维), U10(无面粉), U12(跨建筑检查), U13(正常应聘), U14(满员拒绝), U15(memory CRUD), E1(官府田闭环), E2(吃饭恢复), E3(每日结算), E4(体力不足), E6(完整生命周期), E7(记忆CRUD) | 核心经济逻辑 + 记忆系统，阻塞 M5 验收 |
| P1 | U4(属性钳制), U7(farm不受影响), U8(不再衰减), U11(吃饭钳制), U16(keyword过滤), E5(满员竞争), E8(autonomy新动作) | 边界场景 + 回归保护 + 扩展功能 |

---

## AC 覆盖矩阵

| 功能模块 | 覆盖用例 |
|----------|----------|
| daily_attribute_decay 基本逻辑 | U1, U2, U3, U4, E3 |
| production_tick gov_farm 生产 | U5, U6, U7, U8, E1, E4 |
| eat_food 三维属性恢复 | U9, U10, U11, E2, E6 |
| assign_worker 跨建筑检查 | U12, U13, U14, E5, E6 |
| memory CRUD | U15, U16, E7 |
| autonomy 新动作 | E8 |
| 完整生命周期闭环 | E6 |

---

## 审核记录

- [x] QA Lead 完成初稿（2026-02-18）
- [ ] Developer 确认可测试性
- [ ] Architect 确认覆盖率

---

**编写日期**：2026-02-18
**编写角色**：QA Lead
**基于设计**：TDD-M5-记忆与城市经济

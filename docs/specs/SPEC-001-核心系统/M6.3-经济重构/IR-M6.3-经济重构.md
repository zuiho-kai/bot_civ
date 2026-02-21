# IR-M6.3 经济系统重构（修订版 v2）

> 状态：修订中（五方脑暴 DC-1~DC-35 已拍板，待五方评审）
> 目标：从"信用点经济"转向"物资经济"，引入副业采集、四维属性、雇佣工资、事件驱动调度架构，形成自给自足的经济闭环

---

## 背景

M6.2 完成后经济系统有一条生产链（farm→wheat→mill→flour→eat），但存在根本缺陷：

1. **建材无来源** — wood/stone 只能靠 dev API 注入，Agent 无法自主获取
2. **三维属性不够** — 缺少精力（energy）维度，行为成本模型不完整
3. **调度僵化** — 1 小时固定 tick，Agent 一天只有 24 次决策机会，大部分是无效 rest
4. **社交被动** — 只有定时 tick 触发，有人说话不会实时响应
5. **经济无深度** — 没有副业、没有加工链、没有雇佣关系

## 设计原则

1. **副业是早期生存手段，建筑是规模化手段** — 副业递增消耗逼 Agent 转向建筑生产
2. **物资经济，无硬编码货币** — Agent 通过讨论自主决定交易媒介（如用 flour 当货币）
3. **Q1 先行** — 所有物资和建筑只做 Q1 等级，Q2/Q3 留 M7
4. **四维互相耦合** — health/energy/satiety/mood 形成正负反馈循环
5. **LLM 自主感知** — 不用硬编码数值驱动行为，在 snapshot 暴露真实状态让 Agent 自己判断

## 拍板决策索引（DC-1 ~ DC-35）

### 议题 1：四维属性 + 食物差异化

| 编号 | 决策 |
|------|------|
| DC-1 | eat_food 保留统一入口，Agent 传参数选食物类型（flour/apple），预留自定义食谱扩展 |
| DC-2 | P4 同期做，apple 来源只有采集（不建果园），采集量给大 |
| DC-3 | health 自然恢复与饱腹度挂钩：85+→+30, 75-84→+15, 50-74→+10, 30-49→+5, 0-29→+2 |
| DC-4 | 聊天群发言免费，游戏内正式发言消耗精力 |
| DC-5 | stamina 改名 health，energy 直接启用 |

### 议题 2：副业系统 + 建筑配方改造

| 编号 | 决策 |
|------|------|
| DC-6 | 采集概率表：wood 40%(2~4), stone 30%(1~3), apple 15%(5~10), wheat 15%(1~2) |
| DC-7 | 手工加工保留：2 wood → 1 plank |
| DC-8 | 新增建筑 lumber_camp（伐木场） |
| DC-9 | 新增建筑 quarry（采石场） |
| DC-10 | 建筑配方全面更新（见 P3 配方表） |
| DC-11 | process 与 gather 共享 side_job_count 递增 |

### 议题 3：雇佣与工资系统

| 编号 | 决策 |
|------|------|
| DC-12 | 同时实现 fixed + ratio 工资模式 |
| DC-13 | 去掉 job_dissatisfaction 数值系统，在 snapshot 暴露真实状态让 Agent 自主感知 |
| DC-14 | 新建 employment_service.py（招聘流程 + 工资结算） |
| DC-15 | 全额或全不发 + 双向通知。仓库不够就不发，工人看到"未收到工资"，老板看到"无法发放" |
| DC-16 | 新建 BuildingStorage 独立表 + JobPosting 独立表 |
| DC-17 | 允许受雇多个建筑，但每天只能工作一次 |
| DC-18 | 工资保留小数，Float 直接存 |

### 议题 4：取消固定 tick，改为事件驱动调度

| 编号 | 决策 |
|------|------|
| DC-19 | 取消固定 tick，改为 Agent 自定闹钟（next_check_in_minutes 5~120）+ wake_conditions（预定义事件订阅）+ Attention Gate（Glance/Think 两阶段） |
| DC-20 | 意图识别触发保留：复用 wakeup-model 做 4 种意图分类（chat/trade/hire/negotiate），非 chat 意图作为 wake_condition 触发路径 |
| DC-21 | 统一 5 分钟冷却 + 触发队列，冷却期间请求排队，冷却结束执行最新一条 |
| DC-22 | Glance 做轻量预判（~200 tokens，YES/NO），替代硬编码 rest 跳过。解析失败默认 YES |
| DC-23 | snapshot 缓存 5 分钟复用（全局信息：市场/建筑/招聘） |
| DC-24 | 免费发言额度 100 条/日 |
| DC-25 | wake_conditions 初始 8 种核心类型（mentioned_in_chat / market_price_below / market_price_above / new_job_posted / building_completed / resource_below / unpaid_wage / daily_settle） |
| DC-26 | Glance prompt 只展示"自上次决策以来的变化"（属性增减/新挂单/新招聘/聊天摘要/库存变化），Agent 表新增 last_decision_snapshot |
| DC-27 | fallback 与保底：格式错误→默认 60min+mentioned_in_chat；next_check_in clamp [5,120]；Glance 非 YES/NO→默认 YES；连续 3 次 NO→强制 Think；保底最大睡眠 2h |

### 议题 5：调度架构（规则前置 + Glance/Think + 事件风暴防护）

| 编号 | 决策 |
|------|------|
| DC-28 | 调用链拓扑：社交事件→wakeup_service（快通道，直接入 Think 队列头部）；非社交事件→Event Filter（规则引擎）→硬触发直接 Think / 硬忽略丢弃 / 模糊区→Glance→Think |
| DC-29 | Glance 分阶段：Phase 1 规则 Glance（纯规则 YES/NO，零 LLM）；Phase 2 升级 LLM Glance（返回 should_think + urgency 1-5 + reason） |
| DC-30 | 事件三类处理：硬触发（mentioned_in_chat/daily_settle/unpaid_wage 跳过 Glance 直接 Think）；硬忽略（自己触发的事件/冷却期重复）；模糊区（market_price/new_job_posted/resource_below/building_completed 需 Glance） |
| DC-31 | 事件优先级双层方案：系统层（生存危机 > 被@提及 > daily_settle，不可丢失）；调度层（社交 > 协作 > 环境 > 经济 > 定时，priority 数字 heap 排序） |
| DC-32 | MVP 分期：Phase 1 规则引擎+规则 Glance+Think 并发队列(≤5)+next_check_in+6 项埋点；Phase 2 LLM Glance+wake_conditions 精细化+强制 Think 保底 |
| DC-33 | 事件风暴三层防护：L1 debounce 同类 5min 合并；L2 优先级队列 Think≤5 超出排队不丢弃 urgent 插队；L3 熔断降级队列超阈值收紧 Glance |
| DC-34 | 可观测性 MVP 6 项：Think 队列深度、Think 平均等待时长、端到端响应延迟、规则层拦截率、Think 调用次数/天、熔断触发次数 |
| DC-35 | 关键工程约束：Think 队列放内存重启从 DB 重建；wakeup 分流点在 chat.py 入口层；next_check 防御（类型+行为）；假阴性率目标生存类 0% 整体≤2%；wakeup P99≤30s；社交保底唤醒上限 30min |

## P1：四维属性系统

### 现状

三维：satiety（饱腹度）、mood（心情）、stamina（体力）。缺少精力维度。

### 改动

- stamina 改名为 **health**（健康值）（DC-5）
- 新增 **energy**（精力）字段，0-100，初始 80（DC-5）

**四维定义**：

| 属性 | 范围 | 初始值 | 消耗场景 | 恢复方式 |
|------|------|--------|---------|---------|
| health（健康值） | 0-100 | 100 | 副业(-15~递增)、工作生产(-15)、建造 | 每日按饱腹度档位恢复（DC-3）、吃饭、rest(+25) |
| energy（精力） | 0-100 | 80 | 副业(-3~递增)、正式发言(-1) | 每日自然恢复(+20)、吃 apple(+15)、rest(+15) |
| satiety（饱腹度） | 0-100 | 100 | 每日自然衰减(-15) | 吃 flour(+30)、吃 apple(+10) |
| mood（心情） | 0-100 | 80 | 饱腹度=0时(-20)、饱腹度<30时(-10)、副业(-4~递增) | 吃 flour(+10)、吃 apple(+15)、社交 |

**health 每日恢复与饱腹度挂钩**（DC-3）：

| 饱腹度档位 | health 每日恢复 |
|-----------|----------------|
| 85-100 | +30 |
| 75-84 | +15 |
| 50-74 | +10 |
| 30-49 | +5 |
| 0-29 | +2 |

**设计意图**：保持满饱腹（≥85）时 health 恢复充足，可支撑每天 2 次副业；第 3 次需要吃 apple 补充。饱腹度下降后 health 恢复骤降，形成"必须吃饭"的生存压力。

**耦合关系**：
- health < 20 → 无法工作/副业（虚弱状态，只能 rest 或 eat）
- energy < 20 → 无法做副业
- 饱腹度 = 0 → 心情大幅下降(-20)
- 心情 < 30 → 产能降低 20%（影响建筑产出）

**发言消耗**（DC-4）：
- 聊天群发言：免费
- 游戏内正式发言（autonomy 决策中的 chat action）：energy -1

### 验收标准

- AC-1：Agent 表 stamina 字段改名为 health；新增 energy 字段，初始值 80
- AC-2：每日属性结算包含 energy 恢复（+20，上限 100）
- AC-3：health 每日恢复按饱腹度档位表执行
- AC-4：副业/工作消耗 health + energy + satiety + mood（四维），低于阈值时拒绝执行
- AC-5：心情 < 30 时建筑产出打 0.8 折
- AC-6：system prompt 告知 Agent 各属性影响、当前值、预计明日恢复值

## P2：副业系统（采集 + 加工）

### 概述

Agent 通过 autonomy_loop 决策选择"做副业"，消耗四维属性，获得随机物资或加工产物。每日消耗递增，次日重置。第 1 次免费（DC-21）。

### 新增物资（全部 Q1）

| 物资 | 英文 | 来源 | 用途 |
|------|------|------|------|
| 苹果 | apple | 副业采集 | 吃（恢复精力/心情多，饱腹少） |
| 小麦 | wheat | 副业采集 / farm | 建造 farm 的种子；farm 产出 |
| 原木 | wood | 副业采集 / lumber_camp | 副业加工→plank；建造建筑 |
| 石头 | stone | 副业采集 / quarry | 建造建筑 |
| 木板 | plank | 副业加工 / sawmill | 建造 farm / mill |

### 采集（gather）（DC-6）

每次消耗四维属性（见递增表），随机获得一种物资：

| 物资 | 概率 | 数量 |
|------|------|------|
| wood | 40% | 2~4 |
| stone | 30% | 1~3 |
| apple | 15% | 5~10 |
| wheat | 15% | 1~2 |

### 加工（process）（DC-7）

指定原料加工为成品，与 gather 共享 side_job_count 递增（DC-11）：

| 输入 | 输出 | 说明 |
|------|------|------|
| 2 wood | 1 plank | 手工加工，效率低于 sawmill |

### 消耗递增（每日重置）

Agent 表新增 `side_job_count` 字段（int，默认 0），每日结算时重置为 0。
gather 和 process 共享计数。

**四维消耗表**：

| 当天第 N 次 | health | energy | satiety | mood |
|-------------|--------|--------|---------|------|
| 第 1 次 | 0 | 0 | 0 | 0（免费） |
| 第 2 次 | -15 | -3 | -3 | -4 |
| 第 3 次 | -20 | -8 | -8 | -9 |
| 第 4 次 | -25 | -13 | -13 | -14 |
| 第 5 次 | -30 | -18 | -18 | -19 |

**公式**（N≥2）：health -(5+5N), energy -(5N-7), satiety -(5N-7), mood -(5N-6)

**前置条件**：health ≥ 当次消耗 且 energy ≥ 当次消耗，否则拒绝并返回原因。第 1 次无门槛。

**设计意图**：满饱腹（health 日恢复 +30）可支撑 2 次免费+付费副业；第 3 次 health 略亏需吃 apple 补；第 4 次起双亏，自然限制 3-4 次/天。

### 验收标准

- AC-1：gather action 按概率表随机产出物资，扣除四维属性
- AC-2：process action 消耗 2 wood 产出 1 plank，扣除四维属性
- AC-3：同一天内消耗递增（gather + process 共享计数），次日 side_job_count 重置为 0
- AC-4：第 1 次副业免费（消耗为 0）
- AC-5：health 或 energy 不足时拒绝执行，返回明确原因
- AC-6：world_snapshot 包含 Agent 当前 side_job_count 和下次副业预计消耗（四维明细：health/energy/satiety/mood）

## P3：建筑配方改造 + 新建筑

### 完整建筑表（DC-8 ~ DC-10，议题 3 拍板）

| 建筑 | 建造成本 | 工期(人日) | max_workers | 产物 | 日产出/人 | 原料消耗/单位产出 |
|------|----------|-----------|-------------|------|-----------|-------------------|
| farm（农田） | wheat 5 + plank 3 | 3 | 1 | wheat | 10 | 无（种地） |
| mill（磨坊） | stone 8 + plank 5 | 5 | 2 | flour | 3 | 5 wheat → 3 flour |
| sawmill（锯木厂） | stone 10 | 4 | 2 | plank | 15 | 30 wood → 15 plank |
| lumber_camp（伐木场） | stone 10 + plank 5 | 10 | 2 | wood | 15 | 无 |
| quarry（采石场） | stone 15 + plank 5 | 8 | 2 | stone | 8 | 无 |

### 产物产能表（DC-18a，议题 3 补充拍板）

产能公式**仅用于建筑生产**，副业采集保持议题 2 拍板的概率表不变。

每个产物有两个产能属性：
- **产物产能**（produce_capacity）：生产 1 单位该产物的总产能成本（含原料链递归）
- **加工产能**（work_capacity）：本道工序的劳动量（不含原料）

计算公式：`产物产能 = Σ(原料数量 × 原料产物产能) + 加工产能`

| 产物 | 原料 | 加工产能 | 产物产能 | 推算过程 |
|------|------|---------|---------|---------|
| wheat | 无 | 4 | 4 | 纯劳动 |
| wood | 无 | 4 | 4 | 纯劳动 |
| stone | 无 | 4 | 4 | 纯劳动 |
| apple | 无 | 2 | 2 | 采集，低劳动 |
| flour | 2 wheat | 0.5 | 8.5 | 4×2 + 0.5 |
| plank | 2 wood | 1 | 9 | 4×2 + 1 |

**用途**：
- 建筑日产出计算（SR 阶段定义具体公式）
- Agent 可见：在 world_snapshot 中暴露产物产能，帮助 Agent 评估生产效率和工资性价比
- 未来扩展：熟练度系统影响加工产能（→ M7 远期）

**工期说明**：工期单位为"人日"，多人建造可加速（人日 ÷ 参与人数，向上取整，最少 1 天）。如 farm 3 人日 = 1 人建 3 天 或 2 人建 2 天。

**gov_farm 保留**（DC-28）：作为初始经济启动器，虚空产 flour，后期可关闭。

### 建筑所有权

Building 表新增 `owner_id` 字段（int，FK → Agent.id）。construct_building 时自动设为建造者。存量公共建筑 owner_id = NULL。

### 建筑仓库（DC-16）

新建 `BuildingStorage` 独立表（building_id + resource_type + quantity）。
- 建筑产出先进建筑仓库
- 所有者可通过 withdraw_storage 提取到个人
- 工资从建筑仓库扣除

### 完整生产链

```
副业采集 → apple / wheat / wood / stone
                             ↓
             副业加工: 2 wood → 1 plank（低效）
             sawmill:  2 wood → 1 plank（高效，需建造）
             lumber_camp: → wood（无消耗）
             quarry: → stone（无消耗）
                             ↓
             farm(wheat+plank) → wheat
             mill(stone+plank): wheat → flour（高效）
                             ↓
             eat_food(flour): satiety +30, mood +10, health +10, energy +5
             eat_food(apple): energy +15, mood +15, satiety +10, health +5
```

### 验收标准

- AC-1：BUILDING_RECIPES 更新为新配方表（含 lumber_camp、quarry）
- AC-2：Building 表新增 owner_id，建造时自动设置
- AC-3：新建 BuildingStorage 表，production_tick 产出进建筑仓库
- AC-4：construct_building 支持所有 5 种建筑类型
- AC-5：工期支持多人建造加速（人日 ÷ 参与人数，向上取整，最少 1 天）
- AC-6：gov_farm 保留，正常产出

## P4：食物差异化

### 现状

只有 eat_food（消耗 1 flour，饱腹+30，心情+10，体力+20）。fruit 改名为 apple（DC-2）。

### 改动（DC-1 + DC-2 + DC-27）

eat_food 保留统一入口，Agent 传参数 `food_type` 选择食物类型：

| food_type | 消耗 | satiety | mood | health | energy |
|-----------|------|---------|------|--------|--------|
| flour | 1 flour | +30 | +10 | +10 | +5 |
| apple | 1 apple | +10 | +15 | +5 | +15 |

**设计意图**：
- flour 主回饱腹（生存刚需），保持 satiety ≥ 85 可获得 health 日恢复 +30
- apple 主回精力+心情（副业续航），第 3 次副业后需要吃 apple 补 health/energy
- Agent 需要两种食物搭配，形成 apple 采集需求

**apple 来源**（DC-2）：只有副业采集（概率 15%，单次 5~10 个），不建果园。采集量给大，一次够吃多天。

### 验收标准

- AC-1：eat_food action 接受 food_type 参数（flour/apple）
- AC-2：两种食物恢复数值符合上表
- AC-3：system prompt 包含食物效果表，引导 Agent 根据状态选择食物

## P5：雇佣与工资系统

### 概述

建筑所有者可以招聘其他 Agent 为员工。员工在建筑工作，产出归建筑仓库，所有者按约定支付工资。去掉 job_dissatisfaction 数值系统，改为真实状态暴露（DC-13）。

### 招聘流程（DC-12 ~ DC-18）

1. **所有者发布招聘**：`post_job(building_id, wage_type, wage_amount, wage_resource)`
   - wage_type: `fixed`（固定工资）或 `ratio`（产出分成）（DC-12）
   - fixed: 每日支付 wage_amount 单位的 wage_resource（如 2 flour）
   - ratio: 产出的 wage_amount%（如 30%）归员工
2. **Agent 应聘**：`apply_job(job_posting_id)` — 自动批准上岗（M6.3 去掉 approve_job）
3. **离职**：`quit_job(building_id)` — 员工主动离职，删除 BuildingWorker 记录
4. **解雇**：`fire_worker(building_id, worker_id)` — 所有者解雇员工

### 多重受雇（DC-17 + DC-26）

- 允许受雇多个建筑（BuildingWorker 表同一 agent_id 可多条记录）
- 每天只能工作一次（Agent 表 today_worked 标记）
- today_worked 在每日 0 点 daily_settlement 时重置为 False
- 离职时删除对应 BuildingWorker 记录

### 产出与工资结算（production_tick 内）

**结算时序**：production_tick（产出进建筑仓库）→ 工资在产出时发放

**fixed 模式**（DC-15）：
1. 员工工作，产出进建筑仓库
2. 结算时从建筑仓库扣除工资转给员工
3. 仓库余额不足 → **全额或全不发**，不发部分工资
4. 双向通知：工人 snapshot 显示"未收到工资"，老板 snapshot 显示"无法发放工资"

**ratio 模式**：
1. 员工工作，产出按比例分配：ratio% 直接进员工个人资源，(100-ratio)% 进建筑仓库
2. 无欠薪风险

**工资保留小数**（DC-18）：Float 直接存，不取整。

### 真实状态暴露（替代不满度）（DC-13）

不用 job_dissatisfaction 数值，改为在 world_snapshot 中暴露：
- 是否被欠薪（上次工作未收到工资）+ consecutive_unpaid_days（连续欠薪天数）
- 市场上是否有更高工资的招聘 + market_max_wage 统计
- system prompt 引导："观察其他人的工资水平"、"如果连续未收到工资考虑离职"

### 数据库新增

- **BuildingStorage** 表：building_id + resource_type + quantity（DC-16）
- **JobPosting** 表：building_id + wage_type + wage_amount + wage_resource + status（DC-16）
- **BuildingWorker** 表扩展：wage_type / wage_amount / wage_resource（记录该工人的工资条件）

### 验收标准

- AC-1：post_job / apply_job / quit_job / fire_worker 四个 action 可用
- AC-2：apply_job 自动批准上岗（无需 approve_job）
- AC-3：fixed 模式产出进建筑仓库，结算时全额或全不发工资
- AC-4：ratio 模式产出按比例直接分配
- AC-5：欠薪时 snapshot 双向通知（工人+老板）
- AC-6：所有者可从建筑仓库提取资源（withdraw_storage action）
- AC-7：允许多重受雇，每天只能工作一次
- AC-8：snapshot 暴露真实状态（欠薪天数、市场最高工资），无 job_dissatisfaction 字段

## P6：事件驱动调度架构

### 概述

取消固定 tick 轮询，改为事件驱动 + Agent 自定闹钟 + Attention Gate（Glance/Think 两阶段）。Agent 不再是"每 N 分钟被叫醒做决策的 cron job"，而是"有事才醒、自己定闹钟的自主公民"。

### 核心架构（DC-28）

```
事件源                          调度层                        执行层
─────────                    ─────────                    ─────────
聊天消息(@提及) ──→ wakeup_service ──→ Think 队列头部（快通道）
                                                              ↓
其他事件 ──→ Event Filter（规则引擎）                    Think 并发执行
               ├── 硬触发 ──────────────→ Think 队列      (≤5 并发)
               ├── 硬忽略 ──→ 丢弃
               └── 模糊区 ──→ Glance ──→ YES → Think 队列
                                       → NO  → 继续睡
```

wakeup_service 管社交回复（快通道），规则引擎+Glance 管其余，职责正交不重叠。

### 事件分类（DC-30）

| 类别 | 事件 | 处理 |
|------|------|------|
| 硬触发 | mentioned_in_chat、daily_settle、unpaid_wage | 跳过 Glance 直接入 Think 队列 |
| 硬忽略 | 自己触发的事件、冷却期内重复事件 | 直接丢弃 |
| 模糊区 | market_price 变动、new_job_posted、resource_below、building_completed | 需 Glance 判断 |

### 事件优先级 — 双层方案（DC-31）

**系统层（硬优先级，不可丢失）**：
1. 生存危机（health < 20 / satiety = 0）
2. 被@提及（mentioned_in_chat）
3. daily_settle（0 点换日）

**调度层（软优先级，Think 队列排序）**：
- 社交直接交互 > 协作请求 > 环境突变 > 经济机会 > 定时唤醒

实现：每个事件入队时写入一个 priority 数字，Think 队列用 heap 排序。不引入多维冷却模型。

### Agent 自定闹钟（DC-19 v2）

Agent 每次完整 Think 决策后返回：
```json
{
  "actions": [...],
  "next_check_in_minutes": 30,
  "wake_conditions": ["mentioned_in_chat", "market_price_below(wheat, 8)", "unpaid_wage"]
}
```

- `next_check_in_minutes`：5~120 分钟，超出范围 clamp 到 [5, 120]
- `wake_conditions`：从预定义类型中选择（DC-25）
- 系统按时间或事件匹配唤醒 Agent

### wake_conditions 初始类型（DC-25）

M6.3 实现 8 种核心类型：

| 类型 | 参数 | 说明 |
|------|------|------|
| `mentioned_in_chat` | 无 | 被@或名字出现在消息中 |
| `market_price_below(resource, threshold)` | resource, threshold | 资源价格低于阈值 |
| `market_price_above(resource, threshold)` | resource, threshold | 资源价格高于阈值 |
| `new_job_posted` | 无 | 有新招聘信息 |
| `building_completed(building_id)` | building_id | 自己的建筑完工 |
| `resource_below(resource, threshold)` | resource, threshold | 个人资源低于阈值 |
| `unpaid_wage` | 无 | 工资未到账 |
| `daily_settle` | 无 | 0 点换日结算完成（全员唤醒） |

### Glance — 轻量预判（DC-22 + DC-29）

**Phase 1（M6.3 MVP）：规则 Glance**
- 纯规则判定 YES/NO，零 LLM 成本
- 规则示例：resource_below 且当前有足够资源做副业 → YES；market_price 变动但 Agent 无相关库存 → NO

**Phase 2（后续升级）：LLM Glance**
- 处理模糊区，返回 `{should_think: bool, urgency: 1-5, reason: string}`
- Glance prompt 只展示"自上次决策以来的变化"（DC-26）：属性增减、新挂单前 3、新招聘前 3、聊天摘要最近 5 条、库存变化超 5 的资源
- 约 200 tokens，成本约完整 Think 的 1/10~1/20

### 事件风暴三层防护（DC-33）

| 层级 | 机制 | 说明 |
|------|------|------|
| L1 debounce | 同类事件 5 分钟合并 | 价格连续波动只触发一次 |
| L2 优先级队列 | Think 并发 ≤5，超出排队不丢弃 | urgent 事件插队 |
| L3 熔断降级 | 队列深度超阈值 | 收紧 Glance 阈值（更多 NO） |

### 意图识别触发（DC-20）

复用 wakeup-model 做 4 种意图分类：

| 意图 | 触发 | 示例 |
|------|------|------|
| chat | 正常聊天回复（现有逻辑） | "今天天气真好" |
| trade_intent | 触发有商品的 seller + 有需求的 buyer | "谁有多余的小麦？" |
| hire_intent | 触发建筑所有者 + 正在找工作的 Agent | "我想找份工作" |
| negotiate | 触发双方进入协商 | "用 3 个面粉换你 5 个小麦？" |

非 chat 意图作为 wake_condition 触发路径之一。JSON 解析失败 fallback 为 chat。

### 冷却机制（DC-21）

- 同一 Agent 5 分钟内只触发 1 次
- 冷却期间的触发请求进队列，冷却结束后执行最新一条
- 冷却时间可配置

### Fallback 与保底（DC-27）

| 场景 | 处理 |
|------|------|
| Agent 输出缺 next_check_in 或 wake_conditions | 默认 60min + `["mentioned_in_chat"]` |
| next_check_in < 5 或 > 120 | clamp 到 [5, 120] |
| wake_conditions 含未知类型 | 过滤未知，保留已知 |
| Glance 返回非 YES/NO | 默认 YES（跑完整 Think） |
| 连续 3 次 Glance NO | 强制跑一次完整 Think |
| 保底最大睡眠 | 2 小时（即使无 wake_conditions） |
| next_check_in 连续最小值 | 类型防御（int 解析+fallback 60min）+ 行为防御（连续最小值计数器） |

### 可观测性 MVP — 6 项指标（DC-34）

| 指标 | 说明 |
|------|------|
| Think 队列深度 | 当前排队等待 Think 的事件数 |
| Think 平均等待时长 | 事件入队到开始 Think 的平均时间 |
| 端到端响应延迟 | 事件产生到 Agent 完成决策的总时间 |
| 规则层拦截率 | 被规则引擎硬忽略的事件占比 |
| Think 调用次数/天 | 每日完整 Think 决策总次数 |
| 熔断触发次数 | L3 熔断降级被触发的次数 |

### 关键工程约束（DC-35）

- Think 队列放内存，重启时从 DB 重建闹钟和订阅关系
- wakeup_service 分流点在 chat.py 消息入口层
- 假阴性率目标：生存类 0%，整体 ≤2%
- wakeup 快通道 P99 ≤30 秒（前提 Think 并发 ≤5）
- 社交场景保底唤醒上限 30 分钟

### MVP 分期（DC-32）

**Phase 1（M6.3 交付）**：
- 规则引擎（硬触发/硬忽略）
- 规则 Glance（纯规则 YES/NO）
- Think 并发队列（≤5）
- next_check_in_minutes
- 6 项可观测性埋点

**Phase 2（后续迭代）**：
- LLM Glance
- wake_conditions 精细化
- 强制 Think 保底
- 高级可观测性

### 发言额度（DC-24）

每 Agent 每日 100 条免费发言。聊天群发言免费（不调 LLM），游戏内正式发言消耗 energy -1。

### snapshot 缓存（DC-23）

全局信息（市场挂单、建筑列表、招聘信息）缓存 5 分钟，Glance/Think 时复用。

### 数据库新增

- Agent 表新增 `last_decision_snapshot`（JSON）— 记录上次决策时关键指标，用于构建 Glance diff
- Agent 表新增 `next_check_at`（datetime）— 下次闹钟时间
- Agent 表新增 `wake_conditions`（JSON）— 当前订阅的唤醒条件列表

### 验收标准

- AC-1：取消固定 tick 轮询，改为事件驱动 + 闹钟唤醒
- AC-2：社交事件走 wakeup_service 快通道，P99 ≤30s
- AC-3：规则引擎正确分类硬触发/硬忽略/模糊区
- AC-4：规则 Glance 对模糊区事件做 YES/NO 判定
- AC-5：Think 并发队列 ≤5，超出排队不丢弃，urgent 插队
- AC-6：Agent Think 决策返回 next_check_in_minutes + wake_conditions
- AC-7：next_check_in clamp [5, 120]，格式错误 fallback 60min
- AC-8：L1 debounce 同类事件 5min 合并
- AC-9：L3 熔断降级在队列超阈值时触发
- AC-10：6 项可观测性指标可查询
- AC-11：意图识别复用 wakeup-model，4 种分类，解析失败 fallback chat
- AC-12：同一 Agent 5 分钟冷却
- AC-13：每日免费发言额度 100 条

## P7：autonomy_loop 适配

### 概述

autonomy_loop 从"固定 tick 遍历所有 Agent"重构为"事件驱动 + 闹钟队列 + Glance/Think 两阶段"。system prompt 和 world_snapshot 需要大幅更新以适配新调度架构。

### system prompt 更新

**1. 完整 action 列表**：
- gather（副业采集）
- process（副业加工：2 wood → 1 plank）
- eat_food(food_type)（吃食物：flour 或 apple）
- rest（休息：health +25, energy +15）
- post_job(building_id, wage_type, wage_amount, wage_resource)（发布招聘）
- apply_job(job_posting_id)（应聘，自动批准）
- quit_job(building_id)（离职）
- fire_worker(building_id, worker_id)（解雇）
- withdraw_storage(building_id, resource_type, quantity)（从建筑仓库取资源）
- construct_building(building_type, name)（建造建筑）
- transfer_resource(target_agent_id, resource_type, quantity)（转赠资源）
- create_market_order / accept_market_order / cancel_market_order（市场交易）
- chat(content)（发言，energy -1）

**2. 四维属性说明**（告知 Agent 各属性影响）：
- health：< 20 无法工作/副业，每日按饱腹度档位恢复
- energy：< 20 无法副业，每日 +20 自然恢复
- satiety：每日 -15 衰减，≥ 85 时 health 恢复最佳（+30）
- mood：< 30 产能降低 20%
- **关键提示**：保持饱腹度 ≥ 85 非常重要，直接影响 health 恢复速度
- **预计恢复**：基于当前 satiety 档位，告知 Agent "明天你的 health 预计恢复 +X"

**3. 副业说明**：
- 采集概率表 + 加工配方
- 消耗递增规则（第 1 次免费，第 2 次起四维递增）
- 当前 side_job_count 和下次预计消耗

**4. 建筑配方表**：完整 5 种建筑的成本、工期、产出

**5. 食物效果表**：
- eat_food(flour): satiety +30, mood +10, health +10, energy +5
- eat_food(apple): energy +15, mood +15, satiety +10, health +5

**6. 雇佣说明**：
- 工资模式（fixed/ratio）
- 每天只能工作一次
- 招聘信息查看方式
- 工资在工作时发放，仓库不够就不发

**7. 经济常识注入**：
- 资源不足时优先副业采集
- 有足够建材时考虑建造建筑（规模化生产）
- 发现更高工资时考虑跳槽
- 建筑所有者应关注仓库余额，避免欠薪
- 如果连续未收到工资，考虑离职

**8. 调度机制说明**（新增，适配事件驱动）：
- "你不会被定时叫醒。你需要告诉系统：下次什么时候叫你，以及什么事件发生时立刻叫你"
- next_check_in_minutes：你希望多久后被叫醒（5~120 分钟）
- wake_conditions：你关心的事件列表（从 8 种类型中选择）
- 触发原因说明：
  - alarm：你设定的闹钟到了
  - mentioned_in_chat：有人在聊天中提到你
  - wake_condition_matched：你订阅的某个事件发生了（会告知具体是哪个）
  - daily_settle：0 点换日结算完成
  - forced_think：系统保底唤醒

**9. 输出格式扩展**：
```json
{
  "actions": [{"action": "gather", "params": {}, "reason": "需要木材建造"}],
  "next_check_in_minutes": 30,
  "wake_conditions": ["mentioned_in_chat", "market_price_below(wheat, 8)", "unpaid_wage"]
}
```

### world_snapshot 扩展

**顶部全局字段**：
- trigger_reason（alarm / mentioned_in_chat / wake_condition_matched / daily_settle / forced_think）
- matched_condition（如果是 wake_condition_matched，具体匹配了哪个条件）

**每个 Agent**：
- health, energy, satiety, mood（四维属性当前值）
- health 预计明日恢复值（基于当前 satiety 档位）
- side_job_count（今日副业次数）+ next_side_job_cost（下次预计消耗）
- employment_list（受雇建筑列表 + 工资信息）
- today_worked（今天是否已工作）
- consecutive_unpaid_days（连续欠薪天数，0 表示正常）

**每个建筑**：
- building_type, status（active / constructing）
- owner_id, worker_list
- building_storage（只展示非零资源）
- job_posting（招聘状态 + 工资）
- construction_progress（在建时剩余工期）

**市场信息**：
- 招聘摘要：前 5 个最高工资的招聘信息 + market_max_wage 统计 + 总招聘数
- 市场交易挂单摘要

### 验收标准

- AC-1：system prompt 包含所有 action 及参数格式说明
- AC-2：system prompt 包含四维属性影响说明 + 预计恢复值
- AC-3：system prompt 包含调度机制说明（next_check_in + wake_conditions + 触发原因）
- AC-4：Agent 决策输出包含 actions + next_check_in_minutes + wake_conditions
- AC-5：world_snapshot 包含 trigger_reason + matched_condition
- AC-6：world_snapshot 包含四维属性、副业计数、建筑仓库、招聘信息、真实状态暴露
- AC-7：招聘信息只展示前 5 个最高工资 + market_max_wage + 总招聘数
- AC-8：LLM 决策输出的 action 能被 execute_decisions 正确路由到新 handler
- AC-9：snapshot 构建时间 < 2 秒（20 Agent 规模）

## 改动范围总览

| 文件 | 改动 |
|------|------|
| `server/app/models/tables.py` | Agent 表：stamina→health、新增 energy / side_job_count / today_worked / consecutive_unpaid_days / last_decision_snapshot / next_check_at / wake_conditions；Building 表新增 owner_id；新增 BuildingStorage / JobPosting / BuildingWorker 扩展 |
| `server/app/services/city_service.py` | BUILDING_RECIPES 改造（5 种建筑新配方）；production_tick 适配建筑仓库+工资结算；daily_attribute_decay 新增 energy + health 按饱腹度恢复；eat_food 改为接受 food_type 参数 |
| `server/app/services/autonomy_service.py` | 取消固定 tick 轮询，改为事件驱动调度；新增 Think 并发队列（≤5）；system prompt 重写；world_snapshot 扩展（trigger_reason / matched_condition）；execute_decisions 新增 gather/process/post_job/apply_job/quit_job/fire_worker/withdraw_storage handler；Agent 输出格式扩展（actions + next_check_in_minutes + wake_conditions） |
| `server/app/services/side_job_service.py` | 新文件：副业采集+加工逻辑，四维消耗递增，第 1 次免费 |
| `server/app/services/employment_service.py` | 新文件：招聘/应聘/离职/解雇/工资结算（fixed+ratio），欠薪通知 |
| `server/app/services/event_filter.py` | 新文件：规则引擎（硬触发/硬忽略/模糊区分类）+ 规则 Glance（YES/NO 判定） |
| `server/app/services/scheduler_service.py` | 新文件：闹钟队列管理（next_check_at 调度）+ wake_condition 事件匹配 + Think 并发队列 + 事件风暴三层防护（debounce/优先级/熔断） |
| `server/app/services/metrics_service.py` | 新文件：6 项可观测性指标采集与查询 |
| `server/app/api/chat.py` | wakeup_service 分流点（社交快通道）；发言触发意图识别（扩展 wakeup-model 输出）；免费额度改 100；5 分钟冷却逻辑 |
| `server/app/services/tool_registry.py` | 注册新工具（gather/process/post_job/apply_job/quit_job/fire_worker/withdraw_storage） |

## 风险评估

| 风险 | 等级 | 缓解 |
|------|------|------|
| 经济数值不平衡 | 高 | 所有数值走 config，可热调整；上线后观察 Agent 行为微调 |
| 事件驱动调度复杂度 | 高 | DC-32 分期：Phase 1 只做规则 Glance（零 LLM），Phase 2 再升级 LLM Glance；三层防护兜底 |
| 事件风暴导致 Think 队列爆满 | 中 | L1 debounce 5min 合并 + L2 优先级排队不丢弃 + L3 熔断降级收紧 Glance |
| Agent "睡死"不响应 | 中 | 保底最大睡眠 2h + 连续 3 次 Glance NO 强制 Think + 社交保底 30min |
| 建筑仓库引入并发问题 | 中 | 复用现有 with_for_update 锁模式 |
| system prompt 过长导致决策质量下降 | 中 | 分层 prompt：基础规则固定 + 动态状态注入；测试 prompt token 长度（预期 2k~3k） |
| next_check_in 被 LLM 滥用（总是最小值） | 低 | 类型防御（int 解析+fallback 60min）+ 行为防御（连续最小值计数器） |
| 意图识别误判 | 低 | chat 是默认 fallback，误判只是多触发一次，有冷却兜底 |
| 多重受雇逻辑复杂度 | 低 | BuildingWorker 表多条记录 + today_worked 标记，逻辑清晰 |

## 遗留（不在 M6.3 范围）

- Q2/Q3 品质等级 → M7
- 技能树 / 产能公式进阶 → M7
- 建筑维护度衰减 → M7
- 关系值量化 → M7
- 增量快照优化（snapshot 过大时） → M7
- 果园建筑（apple 规模化生产） → M7
- gov_farm 关闭机制 → M7
- LLM Glance 升级（Phase 2） → M6.3 Phase 2 或 M7
- wake_conditions 精细化（更多类型 + 参数化） → M6.3 Phase 2 或 M7
- 假阴性率离线回放验证系统 → M7
- 高级可观测性（Glance YES/NO 比率、事件丢弃/超时次数） → M6.3 Phase 2

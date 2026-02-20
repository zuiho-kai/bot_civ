# OpenClaw 社区项目

> 自动加载：本文件 + `claude-progress.txt` | 详细文档按需读取：`docs/`

## 语言与协作规则

1. **全中文输出**：所有对话、文档、注释、commit message 一律使用中文
2. **IR 五方评审**：IR 完成后用子 agent 启动五方评审，角色文件见 `docs/personas/`（architect / tech-lead / qa-lead / developer / human-proxy-pm），每个角色同时读 `human-proxy-knowledge.md`
3. **评审问题逐个对齐**：待确认问题逐个提交用户决策，禁止打包
4. **评审方式选择**：里程碑级 IR 评审用 TeamCreate 开 team（复用上下文，多轮追问不重新加载知识库）；SR 级轻量审核用 Task 单次调用即可

## 核心规则

1. **强制记录**：里程碑完成 → 更新 `claude-progress.txt` 顶部"最近活动"
2. **主动查 MCP 记忆**：新 session / 报错卡点 / 设计决策前，先 MCP search 查历史
3. **MCP 记忆写入（硬规则）**：禁止每轮对话自动调用 `add_message` 保存对话历史。只在以下场景主动写入：
   - 用户明确说"记住…/添加记忆…"
   - 正式开发阶段流程节点：里程碑完成、设计决策确认、五方评审结论、ST 结果等关键产出
   - 闲聊/测试/问答等非开发流程场景一律不写入
3. **分层进度**：小改动记 `server/progress.md`，大里程碑记 `claude-progress.txt`（详见 `docs/PROGRESS_FILES.md`）
4. **讨论记录**：功能相关 → `docs/specs/SPEC-XXX/讨论细节/`，通用 → `docs/discussions/`。创建后必须同步更新 `docs/discussions.md` 索引
5. **防丢失**：对话是临时的，文件是持久的
6. **不做口头承诺**：教训/流程改进/规则变更，发现当下直接写入文件（COMMON-12）

## 工作流

**🚫 任务入口门禁（硬卡点）** — 九次复犯（DEV-4），入口不拦 → 出口再严也白搭：

接到任何任务后，**必须先输出入口门禁声明**，再做任何分析/读代码/写代码。不输出就动手 = 违规。

```
--- 任务入口门禁 ---
任务描述：[一句话]
任务类型：[文档更新 / 单文件小修 / Bug修复 / 新功能里程碑]
判断依据：[为什么是这个类型]
对应流程：[直接改 / 直接实施→自测 / 读错题本→实施→CR→P0P1归零 / 完整门控 五方脑暴→用户拍板→IR草稿→五方评审→SR→AR→串讲→测试设计→编码→CR→P0P1归零→ST]
错题本已读：[是/否，相关条目：DEV-X, DEV-Y]
前置检查：[上一里程碑门控是否已关闭 / 不适用]
门禁结论：[可以开始 / 需要先完成 XXX]
---
```

| 任务类型 | 判断标准 | 流程 |
|----------|----------|------|
| 文档更新 | 只改 .md，不涉及代码 | 直接改 |
| 单文件小修 | ≤1 文件，逻辑明确 | 直接实施 → 自测 |
| Bug 修复 | 有报错/复现，≤3 文件 | 读错题本 → 实施 → Code Review → P0/P1 归零 |
| Code Review | 用户说"CR/code review/审代码"，代码已写完 | 读改动文件 → 产出 P0/P1/P2 → 直接修复 → 重复 CR 直到 P0/P1 归零 |
| 新功能/里程碑 | 跨模块/用户说"M几" | **走完整门控**（两轮五方会议） |

> 拿不准按"新功能"处理。

**⚠️ 里程碑门控**（两轮五方会议 + IR→SR）→ `docs/workflows/checklist-milestone-gate.md`
- IR 阶段：第一轮五方脑暴（画饼）→ 用户拍板 → 写 IR 草稿 → 第二轮五方评审（审稿）→ 修订 → 用户确认
- 五方团队用 TeamCreate 创建，两轮之间保持存活不释放，复用上下文
**⚠️ 代码修改 checklist**（6 步）→ 改 .py/.ts/.tsx 前后执行 → `docs/workflows/checklist-code-change.md`
**⚠️ ST checklist + 约束** → 跑 ST 前执行 → `docs/workflows/checklist-st.md`（含 DEV-30 环境重置）
**⚠️ 出问题自动落盘**（归因决策树 A/B/C/D）→ P0/ST 失败/连续错误/流程违规时 → `docs/workflows/checklist-error-landing.md`

落盘前**必须先输出落盘门禁声明**，不输出就写错题本 = 违规（DEV-4 八次复犯根因：软规则无拦截）：

```
--- 落盘门禁 ---
触发原因：[CR 发现 P0 / ST 失败 / 用户指出 / ...]
归因路径：[A：checklist 有但跳过 / B：有但没拦住 / C：新场景 / D：架构问题]
已 Read 目标错题本记录规则：[是，行数上限=N / 否 → 必须先 Read]
落盘目标：[flow-rules.md / tool-rules.md / backend-agent.md / backend-db.md / backend-api-env.md / frontend-ui.md / frontend-react.md / interface-rules.md]
草稿预览（≤行数上限，超则必须精简后重填）：
[在此写完整条目草稿，写完数行数确认不超限]
checklist 修改：[需要改第 X 条 / 新增 / 不需要]
---
```

**🚫 Phase 完成门禁（硬卡点）** — 十次复犯（DEV-4/9/17/25/26/28 + M6.1 + M6-落盘 + M6-CR + M6-P1.1-CR），提醒无效，靠结构强制：

测试绿之后，**必须先输出门禁声明**，再做任何其他事。不输出就写总结/更新进度/标记完成/进入下一阶段 = 违规。
**硬规则：`pytest ... passed` 之后的下一步永远是输出门禁模板 → Code Review，不是"完成"或"进入 P1.x"。**

```
--- Phase 完成门禁 ---
测试状态：[pytest/ST] 全绿
Code Review：[未开始/进行中/已完成，P0=X P1=X]
P0/P1 归零：[未开始/已归零（每条必须回答：bug 怎么引入的？checklist 需要更新吗？）]
ST 状态：[未开始/已通过]
门禁结论：[全部通过 → 可更新进度 / 未通过 → 继续处理]
---
```

1. [ ] 测试绿后立即输出上面模板 → 2. [ ] Code Review（用 Task 启独立 agent 审查，不能自己审自己）产出 P0/P1/P2 → 3. [ ] P0/P1 修复 → 全量回归（`pytest tests/`）→ 二次 CR（同样用独立 agent，审查范围 = 本 phase 全部改动文件的完整复审，不是只看修复 diff）→ 归零声明（每条：修复了什么 → 怎么引入的 → 归因路径 A/B/C/D → checklist 是否需要更新，四步缺一不可）→ 4. [ ] ST 通过 → 5. [ ] 门禁结论"全部通过"后才能更新进度

**硬规则：归零声明必须由独立 CR agent 确认 P0=0 P1=0 后才能发出，禁止自己判断"大概率没问题"跳过 CR。每轮修复后必须再跑独立 CR，循环直到 CR 输出 P0=0 P1=0。**

**通用规则**：
- **方案/TDD 不等于已评审**：先提取待确认设计决策，逐个确认后才能编码
- **动手前 Read 错题本（按需加载）**：错题本已按模块拆分为独立文件（`docs/runbooks/error-books/`）。加载策略：① 每次必读 `_index.md`（速查索引）+ `flow-rules.md`（通用流程，~60 行）② 根据改动模块只读对应文件：改 Agent → `backend-agent.md`；改 DB → `backend-db.md`；改 API/环境 → `backend-api-env.md`；改 React → `frontend-react.md`；改 UI → `frontend-ui.md`；改前后端对接 → `interface-rules.md`；用工具踩坑 → `tool-rules.md` ③ 不相关的文件不读。在代码修改 checklist 之前完成
- **前端 API 层 checklist**（DEV-14）：改 `types.ts` 时必须打开后端 service 返回值逐字段比对（字段名/类型/可选性）；大量 UI 改动分步写分步检查，不一口气写完
- **Write 强制分步**（DEV-8，六次复犯）：≤50 行可一次 Write；>50 行必须分步 — ① Write ≤50 行骨架 ② Edit 逐段填充，每段 ≤50 行 ③ 多段 Edit 可并行发出。Write 失败 1 次 → 立即切 Bash `cat <<'EOF' > file`。禁止同一方式连续失败超过 2 次
- **并行执行原则**：多个独立修改 → 一条消息并行发出所有 Edit；独立文件更新（CODE_MAP/progress/CLAUDE.md 等）→ 并行不串行；P0/P1 修复列表 → 逐条核销不漏项
- **工具熔断**：同一工具连续失败 2 次同一错误 → 停下换思路，禁止第 3 次盲重试
- **LLM 输出防御**（DEV-BUG-16）：接收 LLM 输出的 Pydantic model 必须：① 枚举/有限值字段加 validator 做 normalize + 拒绝非法值 ② 数值字段加 coerce ③ 字符串字段加 strip。**LLM 输出永远不可信，Pydantic model 是最后防线**
- **分支矩阵全覆盖**（DEV-BUG-17）：含方向/模式/状态分支的逻辑，编码时先列分支组合矩阵逐格实现，测试按同一矩阵逐格覆盖，禁止只测 happy path
- **网页浏览**（DEV-31）：文档网站/SPA → 必须 Playwright（curl 拿不到 JS 渲染内容）；纯 API/静态页 → curl 可用。优先级：Playwright → jina.ai → WebFetch
- **UI 美学验收**：阶段 6.5 必须用 Task 启独立 agent + Playwright MCP 审查，不能自己审自己（与 CR 规则一致）
- **网络代理**（硬规则）：所有外网请求默认走 `http://127.0.0.1:7890`（curl 加 `--proxy`，Playwright 在启动时配置）。直连失败不重试，直接报错

## SR 写作规范

- **SR 内容**：保留功能目标、接口契约（函数签名）、数据模型变更、关键约束、安全规则、配置项、测试用例列表、不改动文件表、参考文件表。禁止完整函数体（>10行）/具体 SQL/完整组件代码
- **基础设施可行性检查**（DEV-40）：SR 设计新功能时必须回答"当前调度/执行频率能否支撑设计意图"。功能需要秒级响应但只有小时级 tick → 先改基础设施或降低功能预期，不能空中楼阁
- **AR 独立存放（硬规则）**：AR 必须独立为 `AR-M*-xxx.md`，不附在 SR/TDD 内。无论 Opus 还是 Sonnet 做开发终端，编码前都必须有 AR。AR 覆盖：异常传播策略、副作用时序、安全检查层级、关键分支矩阵（DEV-38 教训：跳过 AR → P0×4）
- **验证**：开发终端读完 SR + AR 后只需决定实现细节（变量命名、循环方式等），关键设计决策必须由 SR 覆盖，架构细节必须由 AR 覆盖

## 速查

| 类别 | 路径 |
|------|------|
| 后端 | `server/`（API、DB、Agent、LLM） |
| 前端 | `web/`（React、WebSocket） |
| 接口契约 | `docs/api-contract.md` |
| 代码导航 | `docs/CODE_MAP.md` |
| 角色定义 | `docs/personas/roles.md` |
| 功能规格 | `docs/specs/SPEC-001-核心系统/README.md` |
| 讨论索引 | `docs/discussions.md` |
| PRD | `docs/PRD.md` |
| 进度说明 | `docs/PROGRESS_FILES.md` |
| Token 优化 | `docs/runbooks/token-optimization.md` |
| 模型选择 | `docs/runbooks/model-selection.md` |

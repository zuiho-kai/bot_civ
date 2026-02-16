# 错题本 — 💻 开发者

> 前后端协作、代码实施、环境踩坑相关的典型错误。

### 记录规则

- **DEV-BUG 条目只写摘要**（场景/根因/修复/防范，各 1-2 行），控制在 10 行以内
- **详细复盘**（时间线、失败方案清单、根因分析）放独立文件 `postmortem-dev-bug-N.md`，错题本里放链接
- **目的**：开发者角色每次加载错题本时只吃 ~150 行，需要查细节时再按需读 postmortem

---

## 协作与流程错误

### DEV-1 后端终端改了前端文件

❌ 后端终端修改 `web/src/components/Chat.tsx`
✅ 后端终端只改 `server/`，前端问题通知前端终端处理
> 职责分离，避免冲突。

### DEV-2 改接口没更新契约文档

❌ 后端改了 `/api/agents` 的返回格式，没更新 `docs/api-contract.md`
✅ 改接口的同时更新 `docs/api-contract.md`，通知前端终端
> api-contract.md 是前后端唯一的协作边界。

### DEV-3 联调问题用双终端来回排查

❌ WebSocket 消息收不到，前端终端查一遍、后端终端查一遍，来回沟通
✅ 跨层问题用 Agent Team 联调（协调者 + 前端调试者 + 后端调试者）
> 简单问题单终端修，跨层问题用 Agent Team。

### DEV-4 复杂功能跳过需求评审

❌ 直接开始写代码，没有 REQ 文档
✅ 新功能先走四方需求评审（阶段1），产出 REQ-XXX.md
> 简单 Bug 可以跳过，复杂功能必须评审。

### DEV-5 实施不遵循 TDD 文档

❌ TDD 定义了接口格式，实施时自己改了字段名
✅ 严格按 TDD 实施，需要改设计先更新 TDD 再改代码
> TDD 是契约，改契约需要走流程。

### DEV-7 把 pytest 单元测试当成 ST（系统测试）验证

❌ 被要求"启动 ST 测试"时，直接跑 `pytest tests/` 单元测试，声称"全绿=验证通过"
✅ ST 测试 = 启动真实服务器 + 调用真实 API + 观察真实行为。pytest 单元测试是 UT，不是 ST
> 单元测试全绿只能证明 mock 环境下逻辑正确，不能证明真实环境下端到端流程可用。ST 必须拉起服务、打真实请求、看真实响应。

**区分清单**:
1. UT（单元测试）: `pytest tests/` — mock 依赖，验证函数逻辑
2. ST（系统测试）: 启动 uvicorn → curl/httpx 调用 API → 检查数据库/WebSocket 广播
3. E2E（端到端测试）: 前后端联调，浏览器/Playwright 驱动完整用户流程

**防范**: 被要求"ST 测试"或"E2E 验证"时，必须拉起真实服务器，不能只跑 pytest。

---

### DEV-6 修复代码时只看 bug 点，不做影响面分析

❌ 改了变量赋值语义（增量→覆盖），没有检查下游引用是否仍成立，导致死代码、语义矛盾
✅ 修复前 grep 所有引用点，逐个确认改动后语义是否成立；改完后做"涟漪推演"
> 每次修复都改变代码结构，改变本身可能引入新的边界问题。目标是 review 循环 ≤2 轮。


**修复前必做检查清单**:
1. grep 被改变量/函数的所有引用点，逐个确认语义是否仍成立
2. 如果改变了赋值语义（增量→覆盖、必传→可选），追踪所有下游消费者
3. 改完后做"涟漪推演"：这个改动会让哪些下游行为变化？
4. 删参数/改签名时，grep 所有调用方 + 测试中的 assert
5. 不靠隐式假设保安全（"反正 id 不重叠"），用显式代码结构保安全（elif/identity check）

**实际案例**（M2-3/4 四轮 review，本应 2 轮完成）:
- 第二轮把 `self.context` 从增量改为覆盖，没顺着想到末尾 append 变成死代码
- broadcast 清理逻辑用 `bot_connections.pop(aid, None)` 无条件执行，靠隐式假设（id 不重叠）保安全
- 每轮修复引入新问题，导致 4 轮 review 才归零

---

## 实际踩坑记录

> 开发过程中遇到的真实问题，持续追加。

### DEV-BUG-1 Windows Python 指向 Store stub

- **场景**: Windows 上直接运行 `python`
- **现象**: exit code 49，弹出 Microsoft Store
- **原因**: 系统 PATH 里 WindowsApps 的 stub 优先于实际安装的 Python
- **修复**: 用实际路径 `$LOCALAPPDATA/Programs/Python/Python312/python.exe` 创建 venv

### DEV-BUG-2 httpx ASGITransport 不触发 lifespan

- **场景**: 用 httpx + ASGITransport 跑 FastAPI 测试
- **现象**: `no such table` 报错
- **原因**: ASGITransport 不触发 FastAPI lifespan，表没建
- **修复**: 测试 fixture 手动 `Base.metadata.create_all` + `ensure_human_agent`

### DEV-BUG-3 Team 联调端口冲突

- **场景**: team-lead 和 backend-verifier 各自启动 uvicorn 绑同一端口
- **现象**: 第二个实例报 `[WinError 10048] 端口已被占用`
- **原因**: 多 agent 并行时没有约定谁负责启动服务
- **修复**: 有状态资源（端口、文件锁）由单一角色管理，启动前先检查 `curl localhost:8000/api/health`

### DEV-BUG-4 Windows curl 中文 JSON body 400

- **场景**: Windows cmd/bash 下 curl 发送含中文的 JSON
- **现象**: 后端返回 400 body parsing error
- **原因**: Windows 终端编码问题，非服务端 bug
- **修复**: 用文件传 body（`curl -d @body.json`）或用 Python/httpx 测试

### DEV-BUG-5 @提及唤醒要求 Agent 有 WebSocket 连接

- **场景**: 人类 @小明 发消息，期望小明自动回复
- **现象**: 消息发出后无回复，唤醒引擎静默跳过
- **原因**: `wakeup_service.process` 中 @提及必唤要求 `aid in online_agent_ids`，而 online 列表来自 WebSocket `connections.keys()`。Agent 是服务端驱动的，不会自己建 WebSocket 连接
- **修复**: @提及必唤去掉 `in online_agent_ids` 检查，Agent 由服务端直接驱动回复

- **溯源分析（为什么讨论阶段没看护住）**:

  这是一个**跨模块语义不一致**问题，讨论阶段每个模块单独看都没问题，合在一起就出了 bug：

  | 阶段 | 遗漏点 |
  |------|--------|
  | 需求评审（REQ-001） | 没有区分"人类在线"和"Agent 可用"两个概念。REQ-001 同时写了"@提及必定唤醒"和"前端通过 WebSocket 连接"，隐含假设所有参与者都走 WebSocket |
  | 架构讨论（agent-architecture.md） | 方案G 决定 Agent 由服务端驱动（不自己建 WebSocket），但没有回头更新唤醒服务的"在线"定义 |
  | 唤醒讨论（wakeup-mechanism.md） | 只定义了三级唤醒规则（@必唤/小模型选人/定时触发），没有定义"候选池"的来源条件，也没有定义"在线"对 Agent 意味着什么 |
  | TDD 设计（TDD-001） | 伪代码中 `WakeupService.process` 没有 `online_agent_ids` 参数，但也没有明确说"Agent 不需要在线检查" |
  | 实施阶段 | 开发者按直觉加了 `online_agent_ids` 过滤，因为 `connections` 字典是现成的"谁在线"数据源 |

  **根因**：方案G 改变了 Agent 的存在方式（从"自己连 WebSocket"变成"服务端驱动"），但唤醒服务的"在线"概念没有跟着更新。

- **防范措施**: 当一个模块的设计前提依赖另一个模块的行为时，TDD 中应明确列出**跨模块依赖假设**。例如唤醒服务应写清楚："候选池来源 = 所有 status=active 的 Agent，而非 WebSocket 连接列表"

### DEV-BUG-6 OpenClaw BotCiv Plugin 连接反复断开（耗时 1.5h）

- **场景**: 编写 OpenClaw botciv channel plugin
- **根因**: 三层叠加 — Node 22 原生 WS 与 Starlette 不兼容 + ws 模块路径找不到 + oc_bot.py 抢连接
- **修复**: `createRequire` 绝对路径加载 ws + 杀旧客户端 + 修消息格式
- **防范**: 先写 10 行脚本验证连接 → 确认无其他客户端占连接 → 确认依赖可用
- **详细复盘**: [postmortem-dev-bug-6.md](../postmortems/postmortem-dev-bug-6.md)

### DEV-BUG-7 SQLite 并发锁定导致测试死循环（耗时 2h+，200 刀）

- **场景**: M2 Phase 1 完整测试，多个 async task 同时写 SQLite
- **根因**: SQLite 默认 `BEGIN DEFERRED`，两个连接同时持有 SHARED 锁升级时死锁，忽略 busy_timeout
- **修复**: `BEGIN IMMEDIATE` 事件监听器 + 合并 fire-and-forget 写入到同一事务 + Windows UTF-8
- **防范规则**:
  1. SQLite + async 必须用 BEGIN IMMEDIATE
  2. 不要用 asyncio.Lock 序列化 aiosqlite 写入（SQL 在后台线程执行）
  3. fire-and-forget 数据库写入是反模式
  4. 两次失败后停下来搜索根因，不要继续猜（三步止血规则，详见 COMMON-9）
- **详细复盘**: [postmortem-dev-bug-7.md](../postmortems/postmortem-dev-bug-7.md)

### DEV-BUG-8 WebSocket 广播 e2e 测试收不到 Agent 回复

- **场景**: e2e 测试通过 WebSocket 发送人类消息，等待 Agent 回复广播
- **根因**: websockets v16 双向 ping 竞争 — LLM 调用耗时 ~23s 超过 ping_interval(20s)，连接被误判死连接关闭
- **修复**: e2e 测试 `websockets.connect()` 增加 `ping_interval=None` + `broadcast()` 增加异常日志
- **状态**: 已修复

### DEV-BUG-9 ST 暴露 batch wakeup 两个 mock 盲区

- **场景**: M2 Phase 4 完成后首次拉起真实服务器调用 batch wakeup API
- **根因**: mock 把真实约束替换成理想值 — ①`scheduled_trigger` 要求 Human 在线但 dev 无 WS 连接 ②Agent model 不在注册表中，`resolve_model` 静默返回 None
- **修复**: dev endpoint 伪造 `online_ids |= {0}` + Agent model 改为注册表中的模型
- **防范**: 每个 Phase 完成后必须跑 ST（真实服务器+真实 API），不能只跑 pytest；关键函数 None 路径必须有显式日志
- **详细复盘**: [postmortem-dev-bug-9.md](../postmortems/postmortem-dev-bug-9.md)

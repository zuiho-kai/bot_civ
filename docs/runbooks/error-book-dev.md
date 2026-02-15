# 错题本 — 💻 开发者

> 前后端协作、代码实施、环境踩坑相关的典型错误。

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

### DEV-BUG-6 OpenClaw BotCiv Plugin 连接反复断开（耗时 1.5h 排查）

- **场景**: 编写 OpenClaw botciv channel plugin，让 OpenClaw 作为 bot_civ 的原生 channel 接入
- **现象**: WebSocket 连接成功后立刻断开，3秒重连一次，无限循环
- **原因（三层叠加）**:
  1. **Node 22 原生 WebSocket 与 FastAPI/Starlette 不兼容**: Node 22 内置的 `globalThis.WebSocket` 连接 Starlette WebSocket 后立刻收到 close code 1006（异常关闭）。而 `ws` 库正常工作。原因未知，可能是 Starlette 的 WebSocket 实现对 HTTP/1.1 upgrade 的处理与 Node 原生实现有差异
  2. **`ws` 模块找不到**: plugin 用 `import WebSocket from "ws"` 但 plugin 目录没有 node_modules，OpenClaw 的 `ws` 在 `/usr/lib/node_modules/openclaw/node_modules/ws`，模块解析找不到
  3. **oc_bot.py 抢连接**: 旧的 `oc_bot.py` 脚本也用 agent_id=1 连接，bot_civ 的连接池管理会踢旧连接（code 4001 Replaced），两个客户端互相踢导致无限重连
- **修复**:
  1. 用 `createRequire` + 绝对路径加载 ws: `require("/usr/lib/node_modules/openclaw/node_modules/ws")`
  2. 杀掉 oc_bot.py，确保只有 plugin 一个 bot 连接
  3. 消息格式从 `{type: "send_message", data: {content}}` 改为 `{type: "chat_message", content}` 匹配 bot_civ 协议
- **反思**:
  - **应该先写最小验证脚本**: 在写 plugin 之前，应该先用 Node 脚本验证 WebSocket 连接是否正常，而不是写完整个 plugin 再调试
  - **不要假设原生 API 等价于库**: Node 22 的 WebSocket 和 `ws` 库行为不同，特别是跟非标准 WebSocket 服务端交互时
  - **多客户端冲突要提前考虑**: bot_civ 的连接池设计是"一个 agent_id 只允许一个 bot 连接"，部署新客户端前应该先停旧的
  - **SSH 长命令不稳定**: `pkill` + `openclaw gateway restart` 组合命令经常导致 SSH 断连（exit 255），应该分步执行或用 systemd 管理

- **时间线复盘（为什么花了这么久）**:

  | 阶段 | 耗时 | 做了什么 | 问题 |
  |------|------|----------|------|
  | 1. 初始部署 | 10min | 传文件、重启 gateway、确认 plugin 加载 | 顺利，plugin 被识别 |
  | 2. ws 模块缺失 | 15min | 发现 `Cannot find module 'ws'`，尝试 npm install 失败（workspace:* 不兼容），决定改用 Node 22 原生 WebSocket | 方向错误 — 应该直接用绝对路径 require |
  | 3. 原生 WS 连接循环 | 30min | 改完原生 WebSocket API，部署，发现不断重连。反复改代码（addEventListener vs .on, event.data vs raw）、传文件、重启 gateway | **最大浪费** — 没有先写最小脚本验证原生 WS 能不能连 Starlette |
  | 4. 排查断连原因 | 20min | 看 bot_civ server 日志发现 `connection open → connection closed`，写 Node 测试脚本，发现原生 WS code 1006，ws 库正常 | 这一步做对了，但应该在阶段 2 就做 |
  | 5. 改回 ws 库 + 抢连接 | 15min | 用 createRequire 绝对路径加载 ws，发现 oc_bot.py 抢连接（4001 Replaced），杀掉 oc_bot.py | |
  | 6. SSH 断连反复重试 | 20min | pkill/kill 命令导致 SSH exit 255，反复等待重连、分步执行 | 应该用 systemd 或 screen/tmux |
  | 7. 最终验证 | 10min | 连接稳定，发消息测试通过 | |

- **根因分析 — 为什么没有一次做对**:

  1. **缺少 spike/PoC 环节**: 直接写完整 plugin 再调试，而不是先用 10 行脚本验证 "Node → bot_civ WebSocket" 这个最基本的假设。如果先验证，阶段 2-4 的 45 分钟可以压缩到 5 分钟
  2. **远程调试循环太慢**: 每次改代码要：本地编辑 → base64 传输 → SSH 重启 gateway → 看日志。一个循环 3-5 分钟。6 次循环就是 30 分钟。应该直接在远程机器上用 vim/nano 改，或者写一个一键部署脚本
  3. **没有提前梳理运行环境**: 不知道 oc_bot.py 还在跑、不知道 gateway 的 systemd 服务名、不知道 Node 22 原生 WS 跟 ws 库的差异。这些都是可以提前调查的
  4. **问题叠加导致误判**: 三个独立问题（ws 模块缺失、原生 WS 不兼容、oc_bot.py 抢连接）同时存在，修了一个以为解决了，结果还有下一个。应该先列出所有可能的失败点再逐一排除

- **改进 checklist（下次写 channel plugin 时）**:
  1. [ ] 先在目标机器上写 10 行 Node 脚本验证 WebSocket 连接
  2. [ ] 确认目标服务没有其他客户端占用连接
  3. [ ] 确认 plugin 的依赖在 OpenClaw 运行时环境中可用
  4. [ ] 准备一键部署脚本（scp + restart），避免手动多步操作
  5. [ ] gateway 用 systemd 管理，不要手动 kill + nohup

### DEV-BUG-7 SQLite 并发锁定导致测试死循环（耗时 2h+，10 次方案迭代）

- **场景**: 运行 M2 Phase 1 完整测试（WebSocket 消息 + Agent 异步回复 + LLM usage 记录）
- **现象**: Agent 回复生成成功，但保存到数据库时报 `database is locked`，消息无法广播，e2e 测试超时
- **原因（根本原因 + 表面原因）**:

  **根本原因**: SQLite 默认使用 `BEGIN DEFERRED` 事务。当两个连接同时持有 SHARED 锁后尝试升级为 RESERVED 锁时，SQLite 检测到死锁并**立即**返回 "database is locked"，**忽略 busy_timeout**。

  **表面原因（并发写入源）**:
  1. WebSocket 主循环保存人类消息（`chat.py` 第 340 行）
  2. `handle_wakeup` 异步任务保存 Agent 回复（`chat.py` 第 194 行）
  3. `_record_usage` fire-and-forget 任务写入 LLM 用量（`agent_runner.py`）
  4. 三者创建独立数据库会话，DEFERRED 事务互相死锁

- **最终修复（方案 10 — BEGIN IMMEDIATE）**:
  ```python
  # app/core/database.py
  from sqlalchemy import event

  engine = create_async_engine(
      f"sqlite+aiosqlite:///{settings.db_path}",
      echo=settings.debug,
  )

  @event.listens_for(engine.sync_engine, "connect")
  def _set_sqlite_pragma(dbapi_connection, connection_record):
      dbapi_connection.isolation_level = None  # 禁用驱动自动事务
      cursor = dbapi_connection.cursor()
      cursor.execute("PRAGMA journal_mode=WAL")
      cursor.execute("PRAGMA busy_timeout=30000")
      cursor.execute("PRAGMA synchronous=NORMAL")
      cursor.close()

  @event.listens_for(engine.sync_engine, "begin")
  def _do_begin(conn):
      conn.exec_driver_sql("BEGIN IMMEDIATE")  # 事务开始时立即获取 RESERVED 锁
  ```

  **附带修复**:
  1. `generate_reply` 返回 `(reply, usage_info)` 元组，不再 fire-and-forget 写 usage
  2. `handle_wakeup` 第三阶段在同一个事务中写入消息 + 扣额度 + 记录 usage
  3. `main.py` 添加 `sys.stdout/stderr.reconfigure(encoding="utf-8")` 解决 Windows GBK 编码错误

- **失败方案清单（为什么前 9 个方案都不行）**:

  | # | 方案 | 为什么失败 |
  |---|------|-----------|
  | 1 | `connect_args={"timeout": 30}` | aiosqlite 不支持此参数 |
  | 2 | WAL 模式 | WAL 允许并发读，但仍然只允许一个 writer |
  | 3 | 连接池配置 | 不影响事务类型 |
  | 4 | NullPool | 每次新连接，更多并发 writer，更容易死锁 |
  | 5 | 分离 DB 会话 | 减少了持锁时间，但 DEFERRED 死锁仍然存在 |
  | 6 | send_agent_message 接受 db 参数 | 减少了会话数量，但并发源仍在 |
  | 7 | 全局 asyncio.Lock | asyncio.Lock 只序列化协程，aiosqlite 的 SQL 在后台线程执行，锁无法覆盖 |
  | 8 | Lock 应用到 _record_usage | 同上，且 Lock 必须包裹整个会话生命周期才有效 |
  | 9 | 统一 usage 写入 | 减少了并发源，但 DEFERRED 死锁根因未解决 |

- **关键认知突破**:

  1. **`asyncio.Lock()` 对 aiosqlite 无效**: aiosqlite 在后台线程执行 SQL，asyncio.Lock 只序列化协程调度，无法阻止两个后台线程同时执行 `BEGIN`
  2. **`busy_timeout` 对 DEFERRED 死锁无效**: 两个连接都持有 SHARED 锁想升级 → SQLite 判定为死锁 → 立即失败，不等待
  3. **`BEGIN IMMEDIATE` 从根本上解决**: 事务开始时就获取 RESERVED 锁，第二个连接会等待（尊重 busy_timeout）而不是死锁

- **排查过程中的额外坑**:

  1. **旧进程未被 kill**: `python main.py` 后台进程从 22:40 一直运行，新代码改了但旧进程还在用旧代码。`ps aux | grep python` 确认进程启动时间很重要
  2. **`__pycache__` 缓存**: 清除缓存后才能确保新代码生效
  3. **Windows GBK 编码**: Agent 回复包含 emoji（☀🌞），`logger.info` 输出时触发 GBK 编码错误，被 `except Exception` 捕获导致 reply 变成 None。表现为"数据库没报错但消息没保存"
  4. **缩进错误**: 去掉 `async with _db_write_lock:` 时内部代码缩进没调整，导致 IndentationError，服务器静默启动失败

- **时间线复盘**:

  | 阶段 | 耗时 | 做了什么 | 问题 |
  |------|------|----------|------|
  | 1. 初始诊断 | 5min | 发现 database is locked，查看日志 | 正确 |
  | 2. 方案 1-4 | 20min | timeout/WAL/连接池/NullPool | 在表面原因上打转，没有理解 DEFERRED 死锁机制 |
  | 3. 方案 5-6 | 15min | 分离会话/传递 db 参数 | 方向对了（减少并发），但没解决根因 |
  | 4. 方案 7-8 | 15min | asyncio.Lock | **最大误区** — 以为 Lock 能序列化 aiosqlite 写入 |
  | 5. 方案 9 | 10min | 统一 usage 写入 | 有效减少并发源，但引入 GBK 编码新问题 |
  | 6. 研究根因 | 10min | 搜索 aiosqlite + SQLAlchemy 并发问题 | **转折点** — 发现 BEGIN IMMEDIATE 方案 |
  | 7. 方案 10 | 5min | BEGIN IMMEDIATE 事件监听器 | 代码正确 |
  | 8. 调试部署 | 20min | 旧进程/缓存/缩进错误/GBK | 非技术问题，但耗时最多 |
  | 9. 最终验证 | 5min | 确认 BEGIN IMMEDIATE 生效，无锁定错误 | 成功 |

- **防范规则**:

  1. **SQLite + async 必须用 BEGIN IMMEDIATE**: 这是 SQLAlchemy 官方文档推荐的配置，不是可选优化
  2. **不要用 asyncio.Lock 序列化数据库写入**: aiosqlite 的 SQL 在后台线程执行，Lock 无法覆盖
  3. **fire-and-forget 数据库写入是反模式**: 所有写入应在同一个事务中完成，或通过队列序列化
  4. **改代码后确认旧进程已停止**: `ps aux | grep python` 检查进程启动时间
  5. **Windows 项目必须在入口设置 UTF-8**: `sys.stdout.reconfigure(encoding="utf-8")`
  6. **删除包裹层（如 async with lock:）时检查内部缩进**

- **🚨 成本反思（烧了 200 刀的教训）**:

  **问题**: 10 次方案迭代，每次"改代码 → 重启 → e2e 测试 → 看日志 → 分析"循环消耗 15-20 刀 token，总计 200 刀。正确做法 15 分钟 15 刀就能解决。

  **根因**: 凭直觉猜方案，没有先研究问题本质。

  **🚨 三步止血规则（遇到不熟悉的技术问题时）**:

  1. **先搜索，不要猜**（5 分钟上限）: 遇到 "database is locked" 这类明确错误信息，第一步是搜索 "aiosqlite SQLAlchemy database is locked"，而不是凭直觉改配置。大多数常见问题都有现成答案。
  2. **最小脚本验证，不要跑完整 e2e**（省 80% token）: 写 10 行 Python 脚本复现并发写入问题，验证方案是否有效。不要每次都启动完整服务器 + 跑 e2e 测试。
  3. **两次失败后停下来重新思考**（硬性规则）: 如果连续两个方案都失败了，说明对问题的理解有误。停下来重新分析根因，不要继续猜。

  **如果遵循这个规则**:
  - 方案 1 失败 → 方案 2 失败 → 停下来搜索 → 找到 BEGIN IMMEDIATE → 写最小脚本验证 → 应用到项目 → 完成
  - 预计耗时 20 分钟，成本 20 刀，节省 180 刀

### DEV-BUG-8 WebSocket 广播 e2e 测试收不到 Agent 回复（遗留）

- **场景**: e2e 测试通过 WebSocket 发送人类消息，等待 Agent 回复广播
- **现象**: 服务器日志确认 Agent 回复已生成、消息已写入数据库、COMMIT 成功，但 e2e 测试客户端收不到 `new_message` 广播，60 秒超时
- **已排除**:
  - ❌ 数据库锁定（已通过 BEGIN IMMEDIATE 解决，日志无 locked 错误）
  - ❌ GBK 编码（已通过 UTF-8 reconfigure 解决，日志无 gbk 错误）
  - ❌ 广播函数本身（`broadcast()` 逻辑正确，遍历所有连接发送）
- **待排查方向**:
  1. **广播时序**: `send_agent_message` 在 `db.flush()` 后调用 `broadcast()`，但 `db.commit()` 在 `handle_wakeup` 中才执行。如果广播时 WebSocket 连接已断开或未就绪，消息会丢失
  2. **e2e 测试 WebSocket 版本**: 系统 Python 的 websockets 库与 venv 版本不同，可能导致连接行为差异（之前出现过 `InvalidMessage` 错误）
  3. **连接注册时序**: e2e 客户端连接后是否已被加入 `human_connections`？如果 `handle_wakeup` 在连接注册完成前就广播，客户端收不到
  4. **asyncio 事件循环**: `handle_wakeup` 是 `create_task` 启动的，广播和 WebSocket recv 可能在同一个事件循环中竞争
- **优先级**: 低（核心功能正常，仅 e2e 自动化测试受影响，可手动通过前端验证）
- **状态**: 遗留，待 M2 Phase 2 排查

- **溯源分析（为什么规划和测试阶段没看护住）**:

  这个问题的根因是 **SQLite + async 并发写入需要 BEGIN IMMEDIATE**，属于技术选型的隐含约束。回溯各阶段：

  | 阶段 | 遗漏点 |
  |------|--------|
  | 需求评审（REQ） | 没有评估 SQLite 在多 async 写入场景下的并发限制。REQ 只关注了功能需求（消息存储、Agent 回复），没有非功能需求（并发写入安全性） |
  | 架构讨论 | 选择 SQLite 时只考虑了"轻量、无需额外服务"，没有讨论"多个 async task 同时写入"的场景。架构文档没有列出 SQLite 的并发约束和必要配置 |
  | TDD 设计 | `database.py` 的 TDD 只定义了 engine 创建和 session 工厂，没有定义事务隔离策略。缺少"SQLite 并发写入配置"这一技术规格 |
  | Code Review | 第三方 code review 没有检查 `create_async_engine` 的 SQLite 特定配置。reviewer 可能也不了解 DEFERRED 死锁问题 |
  | 测试设计 | 单元测试只测了单连接读写，没有并发写入测试。e2e 测试只验证了"消息能发能收"的 happy path，没有并发压力测试 |

  **根因**: SQLite + aiosqlite 的 `BEGIN IMMEDIATE` 配置是一个**技术选型的隐含约束**，不是功能 Bug。它不会在单连接测试中暴露，只在多个 async task 同时写入时才触发。当前的评审和测试流程没有覆盖"技术选型的并发安全性"这个维度。

- **防范措施**:
  1. **架构选型时列出技术约束清单**: 选择 SQLite 时应同时记录"必须配置 WAL + BEGIN IMMEDIATE + busy_timeout"，写入架构文档
  2. **TDD 增加非功能规格**: 数据库模块的 TDD 应包含事务隔离策略、并发配置等技术规格，不只是表结构和 API
  3. **Code Review checklist 增加数据库并发项**: "SQLite 是否配置了 BEGIN IMMEDIATE？" "是否有 fire-and-forget 的数据库写入？"
  4. **测试增加并发写入场景**: 至少一个测试用例模拟 2-3 个 async task 同时写入数据库

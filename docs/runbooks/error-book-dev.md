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

### DEV-BUG-7 SQLite 并发锁定导致测试死循环（耗时 40min）

- **场景**: 运行 M2 Phase 1 完整测试（包括 e2e WebSocket 消息测试）
- **现象**: 测试运行 40 分钟后终端崩溃，期间无明显进展
- **原因（三层问题）**:
  1. **SQLite 默认配置不支持并发**: `create_async_engine` 没有设置 `timeout` 和 `check_same_thread`，多个 WebSocket 连接 + Agent 异步回复导致 `database is locked` 错误
  2. **Agent 回复无法保存**: Agent 成功生成回复，但保存到数据库时遇到锁定错误，回复无法广播给客户端
  3. **测试挂起等待**: e2e 测试等待 Agent 回复（60秒超时 × 10次循环），但回复永远不会到达，测试一直挂在那里
- **修复**:
  ```python
  # app/core/database.py
  engine = create_async_engine(
      f"sqlite+aiosqlite:///{settings.db_path}",
      echo=settings.debug,
      connect_args={"timeout": 30, "check_same_thread": False}
  )
  ```
- **反思 — 为什么陷入 40 分钟死循环**:
  1. **没有及时检查日志**: 测试运行 2-3 分钟无响应时应该立即检查 `server.log`，而不是等待 40 分钟
  2. **没有设置合理超时**: 应该给测试设置明确的超时（2-5 分钟），超时后立即停止并诊断
  3. **没有识别"卡住"信号**: e2e 测试只收到心跳没有实际消息 → 明显异常，应该立即停止
  4. **可能重复执行相同操作**: 测试失败后可能尝试重新运行，但没有先修复根本问题

- **正确处理流程**:
  ```
  1. 运行测试（设置 2-5 分钟超时）
     ↓
  2. 如果超时/无响应
     ↓
  3. 立即停止测试
     ↓
  4. 检查日志（tail -100 server.log）
     ↓
  5. 识别错误（database locked）
     ↓
  6. 修复根本问题（数据库配置）
     ↓
  7. 重新测试验证
  ```

- **防范规则（🚨 2 分钟规则）**:
  - 任何测试/操作如果 **2 分钟内没有进展** → 立即停止
  - 检查日志，不要盲目等待或重试
  - 所有长时间运行的命令必须设置 `timeout` 参数
  - 识别死循环信号：只有心跳无数据、CPU 高无输出、日志重复相同错误

- **时间线复盘**:

  | 阶段 | 耗时 | 做了什么 | 问题 |
  |------|------|----------|------|
  | 1. 启动测试 | 5min | 运行 M2 Phase 1 测试，包括 e2e WebSocket 测试 | 测试启动正常 |
  | 2. 等待测试完成 | 35min | 测试挂起，只收到心跳，没有 Agent 回复，但一直等待 | **最大浪费** — 应该 2 分钟后就检查日志 |
  | 3. 终端崩溃 | - | 40 分钟后终端崩溃 | 可能是错误堆积导致 |

  **根因**: 没有遵循"2 分钟无进展立即诊断"原则，盲目等待测试完成

- **改进 checklist（运行集成测试时）**:
  1. [ ] 所有测试命令设置明确超时（pytest: 120s, e2e: 180s）
  2. [ ] 测试启动后用 `tail -f server.log` 实时监控
  3. [ ] 2 分钟内无进展 → 立即停止并检查日志
  4. [ ] 识别异常信号：只有心跳、重复错误、CPU 高无输出
  5. [ ] 修复根本问题后再重试，不要盲目重复相同操作

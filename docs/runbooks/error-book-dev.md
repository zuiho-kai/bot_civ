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

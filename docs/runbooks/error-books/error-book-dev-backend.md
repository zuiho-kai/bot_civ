# 错题本 — 💻 开发者 / 后端专属

> **记录规则**：本文件只记录纯后端问题（数据库、API、LLM、Agent）。跨前后端通用教训写 `error-book-dev-common.md`，纯前端问题写 `error-book-dev-frontend.md`。每条控制在 **5 行以内**（❌/✅/一句话根因），详细复盘放 `postmortems/postmortem-dev-bug-N.md`，错题本里只放链接。

---

## 流程规则

### DEV-10 SQLite + async 必须用 BEGIN IMMEDIATE

❌ 默认 `BEGIN DEFERRED`，多连接同时持有 SHARED 锁升级时死锁；fire-and-forget 写入是反模式
✅ 用 `BEGIN IMMEDIATE` 事件监听器，合并写入到同一事务；不要用 asyncio.Lock 序列化 aiosqlite
> 案例：DEV-BUG-7。详见 [postmortem-dev-bug-7.md](../postmortems/postmortem-dev-bug-7.md)

### DEV-11 跨模块语义假设不一致（"在线"定义）

❌ 模块 A 改变了核心概念含义（Agent 从"自己连 WebSocket"变成"服务端驱动"），依赖该概念的模块 B 没同步更新
✅ 当架构决策改变某个概念的语义时，回溯所有依赖该概念的模块，更新其前提假设
> TDD 中应明确列出跨模块依赖假设。案例：DEV-BUG-5。

---

## 后端踩坑记录

#### DEV-BUG-1 Windows Python 指向 Store stub

- **场景**: Windows 上直接运行 `python`
- **现象**: exit code 49，弹出 Microsoft Store
- **原因**: 系统 PATH 里 WindowsApps 的 stub 优先于实际安装的 Python
- **修复**: 用实际路径 `$LOCALAPPDATA/Programs/Python/Python312/python.exe` 创建 venv

#### DEV-BUG-2 httpx ASGITransport 不触发 lifespan

- **场景**: 用 httpx + ASGITransport 跑 FastAPI 测试
- **现象**: `no such table` 报错
- **原因**: ASGITransport 不触发 FastAPI lifespan，表没建
- **修复**: 测试 fixture 手动 `Base.metadata.create_all` + `ensure_human_agent`

#### DEV-BUG-3 Team 联调端口冲突

- **场景**: team-lead 和 backend-verifier 各自启动 uvicorn 绑同一端口
- **现象**: 第二个实例报 `[WinError 10048] 端口已被占用`
- **原因**: 多 agent 并行时没有约定谁负责启动服务
- **修复**: 有状态资源（端口、文件锁）由单一角色管理，启动前先检查 `curl localhost:8000/api/health`

#### DEV-BUG-4 Windows curl 中文 JSON body 400

- **场景**: Windows cmd/bash 下 curl 发送含中文的 JSON
- **现象**: 后端返回 400 body parsing error
- **原因**: Windows 终端编码问题，非服务端 bug
- **修复**: 用文件传 body（`curl -d @body.json`）或用 Python/httpx 测试

#### DEV-BUG-5 @提及唤醒要求 Agent 有 WebSocket 连接

- **场景**: 人类 @小明 发消息，期望小明自动回复
- **现象**: 消息发出后无回复，唤醒引擎静默跳过
- **原因**: `wakeup_service.process` 中 @提及必唤要求 `aid in online_agent_ids`，而 Agent 是服务端驱动的，不会自己建 WebSocket 连接
- **修复**: @提及必唤去掉 `in online_agent_ids` 检查，Agent 由服务端直接驱动回复

#### DEV-BUG-6 OpenClaw BotCiv Plugin 连接反复断开（耗时 1.5h）

- **场景**: 编写 OpenClaw botciv channel plugin
- **根因**: 三层叠加 — Node 22 原生 WS 与 Starlette 不兼容 + ws 模块路径找不到 + oc_bot.py 抢连接
- **修复**: `createRequire` 绝对路径加载 ws + 杀旧客户端 + 修消息格式
- **详细复盘**: [postmortem-dev-bug-6.md](../postmortems/postmortem-dev-bug-6.md)

#### DEV-BUG-7 SQLite 并发锁定导致测试死循环（耗时 2h+，200 刀）

- **场景**: M2 Phase 1 完整测试，多个 async task 同时写 SQLite
- **根因 & 修复**: 见流程规则 DEV-10
- **详细复盘**: [postmortem-dev-bug-7.md](../postmortems/postmortem-dev-bug-7.md)

#### DEV-BUG-8 WebSocket 广播 e2e 测试收不到 Agent 回复

- **场景**: e2e 测试通过 WebSocket 发送人类消息，等待 Agent 回复广播
- **根因**: websockets v16 双向 ping 竞争 — LLM 调用耗时 ~23s 超过 ping_interval(20s)，连接被误判死连接关闭
- **修复**: e2e 测试 `websockets.connect()` 增加 `ping_interval=None` + `broadcast()` 增加异常日志

#### DEV-BUG-9 ST 暴露 batch wakeup 两个 mock 盲区

- **场景**: M2 Phase 4 完成后首次拉起真实服务器调用 batch wakeup API
- **根因**: mock 把真实约束替换成理想值
- **修复**: dev endpoint 伪造 `online_ids |= {0}` + Agent model 改为注册表中的模型
- **详细复盘**: [postmortem-dev-bug-9.md](../postmortems/postmortem-dev-bug-9.md)

#### DEV-BUG-12 Agent model 字段与 MODEL_REGISTRY 不匹配导致静默

- **场景**: E2E 测试 @Alice 唤醒成功但无回复
- **根因**: Alice model=`gpt-4o-mini` 不在 MODEL_REGISTRY，`resolve_model` 返回 None → 静默
- **修复**: 改 model 为注册表中的 `stepfun/step-3.5-flash`
- **详细复盘**: [postmortem-dev-bug-12.md](../postmortems/postmortem-dev-bug-12.md)

#### DEV-BUG-14 OpenRouter 免费模型限流导致 wakeup 静默失败

- **场景**: wakeup-model 配置 `google/gemma-3-12b-it:free`，Agent 唤醒流程无响应
- **根因**: OpenRouter 免费模型频繁 429 限流，`call_wakeup_model` 捕获异常返回 "NONE" → 静默跳过
- **修复**: 改为付费版 `google/gemma-3-12b-it`，去掉 `:free` 后缀
- **防范**: 免费模型只用于开发调试，生产/demo 场景必须用付费模型；wakeup 失败应有明显日志告警而非静默
- **OpenRouter `:free` 模型限额（官方文档）**: 20 RPM；充值<10 credits → 50 次/天；充值≥10 credits → 1000 次/天；多账号/多 key 不能绕过（全局管控）；不同模型有独立限额可分散负载
- **调用放大问题**: 1 条 @3人消息 → wakeup 选人(1) + Agent 回复(3) + 连锁 wakeup 判断(3) + 可能的额外连锁 = 7~9 次/分钟，直接撞 20 RPM 墙。需要给 `_maybe_trigger` 加概率门控或全局冷却

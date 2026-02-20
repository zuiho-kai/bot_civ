# 错题本 — 后端/Agent

### 记录规则

- **DEV-BUG 条目**：场景/根因/修复/防范，各 1-2 行，控制在 **8 行以内**
- **DEV 条目**：❌/✅/一句话解释，控制在 **5 行以内**
- 详细复盘放 `../postmortems/`，这里只放链接

### DEV-11 跨模块语义假设不一致（"在线"定义） `🟢`

❌ 模块 A 改变了核心概念含义（Agent 从"自己连 WebSocket"变成"服务端驱动"），依赖该概念的模块 B 没同步更新
✅ 当架构决策改变某个概念的语义时，回溯所有依赖该概念的模块，更新其前提假设
> TDD 中应明确列出跨模块依赖假设。案例：DEV-BUG-5。

#### DEV-BUG-5 @提及唤醒要求 Agent 有 WebSocket 连接 `🟢`

- **场景**: 人类 @小明 发消息，期望小明自动回复
- **现象**: 消息发出后无回复，唤醒引擎静默跳过
- **原因**: `wakeup_service.process` 中 @提及必唤要求 `aid in online_agent_ids`，而 Agent 是服务端驱动的
- **修复**: @提及必唤去掉 `in online_agent_ids` 检查

#### DEV-BUG-6 OpenClaw BotCiv Plugin 连接反复断开（耗时 1.5h） `🟢`

- **场景**: 编写 OpenClaw botciv channel plugin
- **根因**: 三层叠加 — Node 22 原生 WS 与 Starlette 不兼容 + ws 模块路径找不到 + oc_bot.py 抢连接
- **修复**: `createRequire` 绝对路径加载 ws + 杀旧客户端 + 修消息格式
- **详细复盘**: [postmortem-dev-bug-6.md](../postmortems/postmortem-dev-bug-6.md)

#### DEV-BUG-8 WebSocket 广播 e2e 测试收不到 Agent 回复 `🟢`

- **场景**: e2e 测试通过 WebSocket 发送人类消息，等待 Agent 回复广播
- **根因**: websockets v16 双向 ping 竞争 — LLM 调用耗时 ~23s 超过 ping_interval(20s)
- **修复**: e2e 测试 `websockets.connect()` 增加 `ping_interval=None` + `broadcast()` 增加异常日志

#### DEV-BUG-9 ST 暴露 batch wakeup 两个 mock 盲区 `🟢`

- **场景**: M2 Phase 4 完成后首次拉起真实服务器调用 batch wakeup API
- **根因**: mock 把真实约束替换成理想值
- **修复**: dev endpoint 伪造 `online_ids |= {0}` + Agent model 改为注册表中的模型
- **详细复盘**: [postmortem-dev-bug-9.md](../postmortems/postmortem-dev-bug-9.md)

#### DEV-BUG-12 Agent model 字段与 MODEL_REGISTRY 不匹配导致静默 `🟢`

- **场景**: E2E 测试 @Alice 唤醒成功但无回复
- **根因**: Alice model=`gpt-4o-mini` 不在 MODEL_REGISTRY，`resolve_model` 返回 None → 静默
- **修复**: 改 model 为注册表中的 `stepfun/step-3.5-flash`
- **详细复盘**: [postmortem-dev-bug-12.md](../postmortems/postmortem-dev-bug-12.md)

#### DEV-BUG-14 OpenRouter 免费模型限流导致 wakeup 静默失败 `🟢`

- **场景**: wakeup-model 配置 `:free` 后缀模型，唤醒无响应
- **根因**: 免费模型 429 限流 + 异常被吞返回 "NONE"；@多人消息有调用放大（1条→7~9次/分钟）
- **修复**: 改付费模型。**防范**：免费模型只用于开发调试

#### DEV-BUG-15 price_target "up" 空市场误判 completed + up/down 不对称 `🟢`

- **场景**: price_target(direction="up") 策略在无市场挂单时
- **根因**: up 分支 else 直接 completed+continue → 挂卖代码不可达（死代码）；down 分支无 else → fall through 到挂卖（偶然正确）
- **修复**: 统一 up/down — 有市场数据且达标 → completed，否则 fall through 到挂卖。消除重复代码
- **防范**: 自己审自己审不出逻辑死代码，CR 必须用独立 agent

#### DEV-BUG-16 LLM 输出 Pydantic model 缺防御性 validator `🟢`

- **场景**: Strategy model 接收 LLM JSON，direction/priority/ttl 无防御
- **根因**: LLM 输出大小写不一致、数值为字符串，Pydantic 不自动 coerce
- **修复**: 枚举字段加 normalize validator，数值字段加 coerce，字符串加 strip
- **防范规则已提升至 CLAUDE.md**（DEV-BUG-16 条目）。归因 C

#### DEV-BUG-17 direction 反向路径逻辑不完整 + 测试只覆盖正向 `🟢`

- **场景**: price_target 分支只实现了 up 方向，down 的两个边界未处理
- **根因**: 编码时未列分支矩阵（direction × 市场状态），测试只覆盖 up happy path
- **修复**: 补 down 分支逻辑 + 7 个测试覆盖 down/空市场/TTL
- **防范规则已提升至 CLAUDE.md**（DEV-BUG-17 分支矩阵全覆盖）。归因 C

### DEV-37 Handler 先扣费后调用外部服务，失败白扣 `🟢`

❌ `_handle_web_search` 先扣 credits 再 await 外部调用，超时/失败时已扣费
✅ 乐观预检 + 悲观扣费：预检余额 → 调用外部服务 → 成功后扣费 + flush
> CR checklist 增加"副作用时序检查：扣费/计数是否在成功路径上"

#### DEV-BUG-19 P1 修复引入新 P1 — 修 bug 时缺边界分析 `🟢`

- **场景**: 修复 8 条 P1 后三次 CR 又冒出 8 条新 P1
- **根因**: P1 修复当"小修"，未对新代码做边界分析（null/作用域/mock）
- **修复**: coerce_int 处理 null；min_price 统一作用域；TTL mock time；补 4 个边界测试
- **防范**: 每条修复必须列影响面 + 边界值分析 + 分支矩阵测试。归因 B

#### DEV-BUG-22 LLM client 资源泄漏 + 外部返回值信任 `🟢`

- **场景**: _extract_memory 升级 LLM 摘要，AsyncOpenAI 未关闭 + response.choices 空时 IndexError
- **根因**: new 外部 client 未用 context manager；信任 API 返回结构不做空值防御
- **修复**: `async with AsyncOpenAI(...) as client` + `if not response.choices: return ""`
- **防范**: 凡 new 外部 client 默认 context manager；外部 API 返回值必做空值/空列表防御

#### DEV-BUG-23 测试 mock 覆盖不完整导致 fallback 链假绿 `🟢`

- **场景**: ST fallback 测试未 patch MODEL_REGISTRY，缺 provider 全不可用 UT
- **根因**: 测试编写时未检查被测函数所有外部依赖是否已 mock；fallback 测试矩阵不全
- **修复**: 补 patch MODEL_REGISTRY + 新增 all_providers_unavailable UT
- **防范**: 每个测试写完检查外部依赖 mock 完整性；fallback 链矩阵：全成功/部分失败/全失败/全不可用

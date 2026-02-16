# Postmortem: DEV-BUG-9 — ST 暴露 batch wakeup 两个 mock 盲区

## 场景

M2 Phase 4 完成后，首次拉起真实服务器调用 `POST /api/dev/trigger-batch-wakeup`。

## 现象

1. `wake_list` 始终为空 — `scheduled_trigger` 要求 `0 in online_agent_ids`，但 dev endpoint 无 WebSocket 连接，online_ids 为空集
2. `dispatched=0` — Agent 创建时 model 填了 `deepseek-chat`，不在 `MODEL_REGISTRY` 中，`resolve_model` 返回 None，LLM 静默跳过

## 修复

1. dev endpoint 伪造 `online_ids |= {0}`
2. Agent model 改为注册表中的 `stepfun/step-3.5-flash`

## 根因

mock 测试的固有盲区 — mock 把真实环境的约束替换成理想值，UT 永远绿，真实环境一跑就挂。

## 溯源分析（为什么设计/开发/QA/mock/review 都没看护住）

| 阶段 | 问题 1（online_ids 语义） | 问题 2（model 注册表） |
|------|--------------------------|----------------------|
| 设计 | `scheduled_trigger` 的"人类在线"没定义清楚。定时触发场景下应该是"最近 N 分钟有人类消息"，不是"有 WebSocket 连接" | Agent 创建 API 没定义 model 字段校验规则，自由文本无约束 |
| 开发 | 复用了 `process()` 的 online_ids 参数语义，没区分"消息触发"和"定时触发" | `resolve_model` 返回 None 时只 log warning 不抛异常，调用方无感知 |
| UT/mock | mock 传入 `{0, 1, 2}` 永远满足前置条件 | mock 了 `resolve_model` 或整个 LLM 调用，永远返回成功 |
| Review | 没追问"dev/定时触发时 online_ids 从哪来" | 没检查"model 字段从用户输入到 LLM 调用的完整链路" |
| QA | 只跑 UT，没有 ST 验证真实集成 | 同左 |

## 本质教训

mock 测试验证"逻辑正确性"，ST 验证"集成正确性"，两者不可互相替代。mock 必然失效的三类场景：

1. **跨模块语义假设**：A 模块的参数含义在 B 模块的调用场景下不成立（online_ids 在定时触发 vs 消息触发中含义不同）
2. **配置/注册表约束**：mock 跳过了真实的配置查找链路（model 字段 → MODEL_REGISTRY → resolve_model → API key）
3. **静默失败路径**：函数返回 None 而非抛异常，mock 环境下不会走到这条路径

## 防范规则

1. **每个 Phase 完成后必须跑 ST**：拉起真实服务器 + 调用真实 API + 检查真实数据库，不能只跑 pytest
2. **关键函数的 None 返回路径必须有显式日志或异常**：`resolve_model` 返回 None 应该在上层有明确的错误响应，而非静默跳过
3. **API 入参校验前移**：Agent 创建时 model 字段应校验是否在 `list_available_models()` 中，在入口拦截而非在 LLM 调用时才发现
4. **UT 中至少有一个"真实配置"测试用例**：不 mock `resolve_model`，用真实的 MODEL_REGISTRY 验证链路（可以 mock 网络调用，但不 mock 配置查找）

# Postmortem: DEV-BUG-12 Agent model 字段与 MODEL_REGISTRY 不匹配导致静默

## 概要

Phase 6 E2E 测试中，@Alice 唤醒链路正常（wakeup model 选中 Alice），但 Agent 始终无回复。根因是 Alice 的 model 字段 `gpt-4o-mini` 不在 `MODEL_REGISTRY` 中，`resolve_model` 返回 None，`generate_reply` 静默返回 `(None, None)`。

## 时间线

1. 发送 `@Alice 你好啊` → trigger 返回 `mentions=[1]`，确认 @提及解析正确
2. 等待 20s → 无回复，怀疑等待时间不够
3. 重启服务器保留日志 → 再次触发 → 日志显示：
   - `[WAKEUP:select] candidates=[(1, 'Alice'), (2, 'Bob')]` ✅
   - `[WAKEUP] model returned: 'Alice'` ✅
   - `[WAKEUP] wake_list=[1]` ✅
   - 之后进入 `generate_reply`，但 `resolve_model("gpt-4o-mini")` 返回 None
   - WARNING 日志 `Model gpt-4o-mini not configured or no API key` 被 SQLAlchemy INFO 淹没
4. 检查 `config.py` MODEL_REGISTRY → 只有 `stepfun/step-3.5-flash`、`arcee/trinity-large-preview`、`wakeup-model`
5. `PUT /api/agents/1` 改 model → 立即修复

## 耗时放大因素

| 因素 | 影响 |
|------|------|
| 每次验证 ~30s（唤醒 14s + LLM 10s） | 盲调 5 轮 = 2.5 分钟空等 |
| 服务器日志重定向到 /dev/null | 前几轮完全看不到中间状态 |
| `resolve_model` 返回 None 只有 WARNING | 被 SQLAlchemy INFO 刷屏淹没，不够醒目 |
| 无 dev debug 接口返回链路中间状态 | 只能从"有没有回复"倒推，无法定位断点 |

## 根因分析

这是 DEV-BUG-9 的同类问题：**测试数据（Agent 的 model 字段）与真实运行环境（MODEL_REGISTRY）不匹配**。

- 创建 Agent 时 model 填了 `gpt-4o-mini`（随意填的占位值）
- UT 全部 mock 了 LLM 调用，不经过 `resolve_model`，所以不会暴露
- 只有 E2E 真实调用才会走到 `resolve_model` → 发现不匹配

## 各阶段遗漏

| 阶段 | 应该做什么 | 实际做了什么 |
|------|-----------|------------|
| Agent 创建 API | 校验 model 字段是否在 MODEL_REGISTRY 中 | 无校验，任意字符串都接受 |
| agent_runner | `resolve_model` 返回 None 时应 ERROR 日志 + 带上下文 | 只有 WARNING，无 agent_id/model_key |
| E2E 测试准备 | 确认测试 Agent 的 model 在注册表中 | 没检查，沿用旧数据 |
| dev endpoint | 应提供 `?debug=1` 返回唤醒+生成链路中间状态 | 只返回 trigger 结果 |

## 改进措施

1. **COMMON-16**: 关键分支失败时日志带上下文，不能静默 return None
2. **后续可选**: Agent 创建/更新 API 校验 model 字段是否在 MODEL_REGISTRY 中（或至少 WARNING）
3. **后续可选**: dev/trigger 加 `?debug=1` 返回唤醒选人 + LLM 调用的中间状态

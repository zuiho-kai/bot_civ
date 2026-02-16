# Postmortem: COMMON-13 ST 测试调试循环低效

## 背景

M2 Phase 4 ST 测试，验证 batch wakeup + 经济扣费 + 记忆提取三个端到端流程。

## 卡点时间线

| 卡点 | 根因 | 浪费轮次 |
|------|------|---------|
| POST /api/agents 被 307 重定向 | FastAPI 尾部斜杠不统一，忘加 `/` | 2 |
| 加 print 调试但看不到输出 | dev endpoint 只返回 JSON，print 在服务器 stdout，curl 看不到 | 3 |
| 记忆提取需要 Agent 回复 5 次 | `EXTRACT_EVERY=5`，ST 没有降低阈值的快捷方式，发了 7 条消息才凑够 | 5+ |
| 调试代码反复加/删/等 reload | 没有统一的 debug 开关，每次手动改代码 | 2 |

总计浪费约 12 轮对话，实际验证逻辑只需 3-4 轮。

## 根因分析

dev endpoint 设计时只考虑了"触发功能"，没考虑"辅助调试"：
1. 返回值只有最终结果，没有中间决策链路
2. 阈值硬编码，ST 测试无法覆盖边界场景
3. FastAPI 尾部斜杠行为不统一，每次都要试错

## 防范规则

1. 所有 dev endpoint 支持 `?debug=1` 参数，返回完整中间状态（online_ids, candidates, model_result 等）
2. 有阈值的功能（如 EXTRACT_EVERY）支持通过 dev API 参数覆盖（如 `?extract_every=1`）
3. FastAPI router 统一 `redirect_slashes=False`，或所有路由统一不带尾部斜杠
4. dev endpoint 的错误路径（wake_list 为空、quota 不足）必须返回具体原因，不能只返回 "no agents to wake"

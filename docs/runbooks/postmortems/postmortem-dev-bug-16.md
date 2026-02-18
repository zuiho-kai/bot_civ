# Postmortem DEV-15：写了 E2E 脚本不当场跑 → 假绿交差

## 背景

写了 `e2e_m4.py`（真实 LLM E2E 脚本），没启动服务器跑一遍就 commit + push，声称"E2E 完成"。`test_e2e_autonomy.py` 全部 mock LLM，本质是集成测试，却标记为"E2E 9/9 passed"。真正启动服务器后发现：端点 404（旧代码）、Agent 为空（无 seed）、LLM 全返回 rest（prompt/模型问题）。

## E2E 验证必做清单

1. 启动真实服务器（确认最新代码，清 pycache）
2. 确认数据 seed（Agent/Job/Item 存在）
3. 确认外部依赖可达（LLM API + 代理）
4. 跑脚本看到真实 LLM 响应（不是 mock）
5. 验证状态变化（DB credits 变了、WebSocket 收到事件）
6. 以上全通过后才能 commit 并声称"E2E 通过"

## 真实 E2E 脚本要求

- 必须包含 seed 逻辑（创建 Agent/Job/Item），不依赖外部手动准备
- mock 测试明确标记为"集成测试"，不混淆为 E2E

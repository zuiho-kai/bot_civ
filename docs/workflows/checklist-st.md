# ST 执行前 checklist + ST 强制约束

> **触发时机**：准备执行 `python e2e_*.py` 或启动 ST 之前。
>
> 三条复犯教训（DEV-7/15/24）：pytest 冒充 ST、E2E 写了不跑、旧服务器没重启。

## 执行前 checklist

1. [ ] **确认是 ST 不是 pytest**：ST = 真实服务器 + 真实网络；pytest = 单元/集成测试，不能替代 ST
2. [ ] **确认服务器状态**：改了 `server/` 下任何 `.py` → 必须 kill 旧进程 + 重启服务器
3. [ ] **E2E 脚本写完必须当场跑**：看到真实响应才算验证，不跑就不算写完

## ST 强制约束

违反任何一条即判定 ST 未通过：

1. **必须拉起真实服务器**：`uvicorn main:app` 或等效命令启动独立进程，禁止用 `ASGITransport`/`TestClient` 等进程内传输代替
2. **必须走真实网络**：HTTP client 连接 `http://localhost:端口`，不允许 `base_url="http://test"` 等虚假地址
3. **必须用真实数据库**：SQLite 文件或 Postgres 实例，禁止纯内存 mock 数据库（测试专用 `.db` 文件可以）
4. **LLM 调用规则**：涉及 Agent 决策/聊天的场景必须走真实 LLM（可用便宜模型如 gpt-4o-mini）；纯经济/资源/CRUD 场景可不调 LLM
5. **WebSocket 验证**：必须用 `websockets` 库建立真实 TCP 连接，禁止用 `starlette.testclient` 的进程内 WebSocket
6. **ST 脚本位置**：`server/e2e_*.py`（独立脚本，非 pytest），用 `python e2e_xxx.py` 执行
7. **pytest 定位**：`server/tests/test_*.py` 是单元/集成测试，允许 mock，但不能替代 ST
8. **ST 不通过不允许**：更新进度文件、进入下一个 Phase、标记任务完成

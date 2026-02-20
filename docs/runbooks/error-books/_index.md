# 错题本速查索引

> **加载规则**：每次必读本文件 + `flow-rules.md`，再根据改动模块读对应文件。

| 编号 | 一句话 | 标签 | 频率 | 文件 |
|------|--------|------|------|------|
| DEV-4 | 跳过流程门控直接编码 | 通用/流程 | 🔴×16 | flow-rules.md |
| DEV-5 | 实施不遵循 TDD 文档 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-6 | 改代码不 grep 引用/不复用 pattern/不对照 TDD | 通用/流程 | 🟡×3 | flow-rules.md |
| DEV-7 | pytest 冒充 ST / E2E 不跑 / 旧服务器没重启 | 通用/流程 | 🟡×2 | flow-rules.md |
| DEV-24 | 更新文档只改局部不扫全文 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-29 | P0/P1 修复列表漏项+执行碎片化 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-32 | 门控表缺序号→TDD 被误当起始动作 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-33 | pytest 冒充 ST + P0/P1 归零跳过归因 | 通用/流程 | 🟡×5 | flow-rules.md |
| DEV-34 | SR 阶段门禁当建议跳过 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-38 | 编码前跳过 AR → 安全/异常/配置全面失守 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-40 | 功能设计脱离基础设施现实 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-41 | 用户要求拉角色但不读角色定义文件 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-42 | 对话开头环境指令未执行就动手改文件 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-43 | CR 与五方评审混淆 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-44 | SR/AR 文档与代码签名不同步 + AR 风险面遗漏 | 通用/流程 | 🟢 | flow-rules.md |
| DEV-3 | 联调问题用双终端来回排查 | 通用/工具 | 🟢 | tool-rules.md |
| DEV-8 | Write 工具调用反复失败 | 通用/工具 | 🔴×5 | tool-rules.md |
| DEV-12 | 外部 CLI 跳过环境探针+串行试错 | 通用/工具 | 🟡×2 | tool-rules.md |
| DEV-13 | 用户说"用 CLI"仍绕路打 REST API | 通用/工具 | 🟢 | tool-rules.md |
| DEV-16 | 调研任务串行搜索 | 通用/工具 | 🟢 | tool-rules.md |
| DEV-31 | 网页搜索走 curl 而非浏览器 | 通用/工具 | 🟢 | tool-rules.md |
| DEV-35 | Stop Hook 持续循环 | 通用/工具 | 🟢 | tool-rules.md |
| DEV-36 | 插件 hook 报错定位慢 | 通用/工具 | 🟢 | tool-rules.md |
| DEV-1 | 后端终端改了前端文件 | 通用/接口 | 🟢 | interface-rules.md |
| DEV-2 | 改接口没更新契约文档 | 通用/接口 | 🟢 | interface-rules.md |
| DEV-11c | 前端凭记忆写后端接口信息 | 前端/接口 | 🟡×2 | interface-rules.md |
| DEV-27 | API 层忽略系统边界防御 | 后端/API | 🟡×2 | backend-api-env.md |
| DEV-10c | E2E fixture 不先 drop_all | 后端/DB | 🟢 | backend-db.md |
| DEV-10b | SQLite+async 必须 BEGIN IMMEDIATE | 后端/DB | 🟢 | backend-db.md |
| DEV-BUG-2 | httpx ASGITransport 不触发 lifespan | 后端/DB | 🟢 | backend-db.md |
| DEV-BUG-7 | SQLite 并发锁定死循环 | 后端/DB | 🟢 | backend-db.md |
| DEV-BUG-21 | 新增 handler 未对齐事务模式 + 先查后改未原子化 | 后端/DB | 🟢 | backend-db.md |
| DEV-11b | 跨模块语义假设不一致 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-5 | @提及唤醒要求 WS 连接 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-6 | Plugin 连接反复断开 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-8 | WS 广播测试收不到回复 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-9 | batch wakeup mock 盲区 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-12 | model 字段与 REGISTRY 不匹配 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-14 | OpenRouter 免费模型限流 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-15 | price_target 空市场误判 completed + up/down 不对称 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-16 | LLM 输出 Pydantic model 缺防御性 validator | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-17 | direction 反向路径逻辑不完整 + 测试只覆盖正向 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-19 | P1 修复引入新 P1 — 修 bug 时缺边界分析 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-22 | LLM client 资源泄漏 + 外部返回值信任 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-23 | 测试 mock 覆盖不完整导致 fallback 链假绿 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-37 | Handler 先扣费后调用外部服务，失败白扣 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-38 | M6 P2 上网工具一次性写出 P0×4+P1×7+P2×7 | 后端/Agent | 🟢 | backend-agent.md |
| DEV-BUG-1 | Windows Python 指向 Store stub | 后端/环境 | 🟢 | backend-api-env.md |
| DEV-BUG-3 | Team 联调端口冲突 | 后端/环境 | 🟢 | backend-api-env.md |
| DEV-BUG-4 | Windows curl 中文 JSON 400 | 后端/环境 | 🟢 | backend-api-env.md |
| DEV-BUG-18 | API 路由重复定义 | 后端/API | 🟢 | backend-api-env.md |
| DEV-8f | 新增 UI 必须双主题验证 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-11f | 反馈消息没有自动清除 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-12f | 多问题批量修复不分类 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-14 | 大量 UI 一口气写完不分步检查 | 前端/UI | 🟡×2 | frontend-ui.md |
| DEV-BUG-11 | UI 颜色硬编码不跟主题 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-BUG-13 | 体验问题修复耗时过长 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-BUG-20 | 美学审查漏检 hover 上下文 + 动画舒适度 | 前端/UI | 🟢 | frontend-ui.md |
| DEV-9 | useEffect 外部连接必须幂等 | 前端/React | 🟢 | frontend-react.md |
| DEV-10f | useEffect 依赖放新建数组→无限循环 | 前端/React | 🟢 | frontend-react.md |
| DEV-15 | _useMock 单例缓存卡死 mock 模式 | 前端/React | 🟢 | frontend-react.md |
| DEV-BUG-10 | StrictMode 双挂载 WS 消息重复 | 前端/React | 🟢 | frontend-react.md |

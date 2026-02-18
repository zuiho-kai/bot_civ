# 错题本 — 💻 开发者 / 通用开发（前后端共用）

> **记录规则**：本文件只记录跨前后端的通用教训（双终端分工、接口契约、工具调用策略、外部 CLI 集成、Git 流程、Code Review 流程等）。纯前端问题写 `error-book-dev-frontend.md`，纯后端问题写 `error-book-dev-backend.md`。每条控制在 **5 行以内**（❌/✅/一句话根因），详细 checklist 和复盘放 `postmortems/postmortem-dev-bug-N.md`，错题本里只放链接。

---

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

### DEV-4 跳过流程门控直接编码（评审/串讲/用户确认）

❌ 跳过需求评审直接写代码；AR 完成后跳过串讲+测试用例设计；拿到完整方案不提取待确认点直接派 agent 开干
✅ 完整门控链：IR → SR → AR → 正向串讲 → 反向串讲 → 测试用例设计 → 编码。方案越完整隐含假设越多，越需要逐项提交用户确认
> 三次复犯（DEV-4/DEV-9/DEV-17）。详见 `development-workflow.md` 完整流程。

### DEV-5 实施不遵循 TDD 文档

❌ TDD 定义了接口格式，实施时自己改了字段名
✅ 严格按 TDD 实施，需要改设计先更新 TDD 再改代码
> TDD 是契约，改契约需要走流程。

### DEV-6 改代码不 grep 全量引用 → 下游断裂（含签名/返回值变更）

❌ 改了变量语义或函数返回值，没 grep 全量引用（生产+测试），导致死代码、unpack 报错、mock 失效
✅ 改签名/语义前 `grep -rn "函数名" server/ tests/ web/`，逐个确认引用是否成立；改完做"涟漪推演"
> 案例：DEV-BUG-6（变量语义）、DEV-21（返回值 2→3 元素，10 处 mock 未同步）。详见 [postmortem-dev-bug-6.md](../postmortems/postmortem-dev-bug-6.md)

### DEV-7 把 pytest 单元测试当成 ST（系统测试）验证

❌ 被要求"启动 ST 测试"时，直接跑 `pytest tests/`，声称"全绿=验证通过"
✅ UT=pytest mock；ST=启动 uvicorn + curl 真实 API；E2E=前后端联调 + Playwright
> 单元测试全绿只能证明 mock 环境下逻辑正确，不能证明真实环境可用。

### DEV-8 Write 工具调用缺少 content 参数反复失败（⚠️ 二次复犯）

❌ 长文档生成时连续发空 Write 调用（无 content），二次复犯
✅ Write 调用前先确认 content 已就绪，没就绪就不发；失败后读错误信息修正，连续 2 次同一错误 → 换思路

### DEV-10 E2E 测试 fixture 只 create_all 不先 drop_all → UNIQUE 冲突

❌ `setup_db` 用 `Base.metadata.create_all` 但不先清理，生产 DB 已有数据时 seed 插入冲突
✅ fixture 先 `drop_all` 再 `create_all`，保证每个测试从空表开始
> 测试隔离是基本功。create_all 对已存在的表是 no-op，不会清数据。

### DEV-11 前端凭记忆写后端接口信息 → 运行时全量不匹配

❌ types.ts 字段名凭记忆写；api.ts 路径/method/param 凭记忆拼 — 字段差一字母=undefined，路径差一段=404
✅ 写前端 API 层和类型时必须打开后端路由+schema 文件逐条比对：字段名、类型、可选性、URL path、HTTP method、param 位置、response 字段名
> 两次复犯（DEV-11 字段层、DEV-22 路径层）。详见 [postmortem-dev-bug-17.md](../postmortems/postmortem-dev-bug-17.md)

### DEV-13 用户说"用 CLI"，仍然自行绕路直接打 REST API

❌ 用户明确说"用 gemini cli"，脚本里还是用 fetch 打 REST；CLI 报错就转 API key 绕路
✅ "用 CLI"= subprocess 是唯一路径，CLI 报错 → 报给用户，不绕路；明确指定 `-m` 避免默认 Pro 耗 quota
> 用户指定的工具 = 硬约束，不是"优先项"。详见 [postmortem-dev-bug-10.md](../postmortems/postmortem-dev-bug-10.md)

### DEV-12 外部进程/CLI 排查：跳过环境探针 + 串行试错 → 大量无效轮次

❌ 直接写脚本遇到 PATH/代理/认证/quota 逐个补救；一次只验证一个假设，每次撞墙等超时才换方向；改了配置没确认进程读的是哪份文件
✅ 集成外部 CLI 前先做环境全景扫描：① which ② HTTPS_PROXY/直连 ③ 认证配置路径 ④ 手动测一条命令。多假设并行验证不串行等超时
✅ 429 有 retryDelay = RPM 限制（等）；无 = 真用尽
> 两次复犯（DEV-12、DEV-20）。详见 [postmortem-dev-bug-10.md](../postmortems/postmortem-dev-bug-10.md)、[postmortem-dev-bug-16.md](../postmortems/postmortem-dev-bug-16.md)

### DEV-14 新功能编码不复用已有 pattern → Code Review 出 P1/P2

❌ 不 grep 同类实现、擅自偏离 TDD、try/except 变量可达性未检查、写完不逐条对照 TDD 自查
✅ 编码前 grep 同类 pattern → 写完逐条对照 TDD → 每个 except 走变量可达性分析
> 详见 [postmortem-dev-bug-11.md](../postmortems/postmortem-dev-bug-11.md)

### DEV-15 写了 E2E 脚本不当场跑 → 假绿交差

❌ 写了 E2E 脚本没启动服务器跑就 commit，mock 测试标记为"E2E passed"
✅ E2E 脚本写完必须当场启动服务器跑，看到真实 LLM 响应才算验证；mock 测试标记为"集成测试"
> 详见 [postmortem-dev-bug-12.md](../postmortems/postmortem-dev-bug-12.md)

### DEV-16 调研任务串行搜索 → 浪费时间，违反 CLAUDE.md 并行规则

❌ 调研"无人值守开发模式"时，把 4 个独立子主题（质量保障、并行开发、调度机制、架构对比）塞进 1 个 subagent 串行搜索
✅ 搜索关键词超过 2 组时，拆成多个并行 Task agent 分头搜索，最后汇总
> CLAUDE.md 第 72 行明确规定"调研/搜索任务必须并行"。根因：把调研看成"一个问题"没做任务分解。判断标准：搜索关键词 ≥ 2 组 → 拆并行 agent。


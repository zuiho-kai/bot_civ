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

❌ 跳过需求评审直接写代码；AR 完成后跳过串讲+测试用例设计；拿到完整方案不提取待确认点直接派 agent 开干；测试绿了直接写总结跳过 Code Review；M6.1 里程碑跳过 IR 评审直接编码，写完代码测试全绿后才发现没做 Code Review；错题本落盘跳过第 2 步"Read 记录规则"直接写 → 格式违规；用户说"code review"，只修已知 bug 没产出 P0/P1/P2 全面审查
✅ 完整门控链：IR → SR → AR → 正向串讲 → 反向串讲 → 测试用例设计 → 编码 → Code Review → P0/P1 归零 → 更新进度。方案越完整隐含假设越多，越需要逐项提交用户确认。落盘流程逐步执行不跳步。CR = 读改动文件 → 产出 P0/P1/P2 → 修复 → 重复直到归零
> 九次复犯（DEV-4/9/17/25/26/28 + M6.1 + M6-错题本落盘 + M6-CR）。

### DEV-5 实施不遵循 TDD 文档

❌ TDD 定义了接口格式，实施时自己改了字段名
✅ 严格按 TDD 实施，需要改设计先更新 TDD 再改代码
> TDD 是契约，改契约需要走流程。

### DEV-6 改代码不 grep 引用 + 不复用 pattern + 不对照 TDD（含 DEV-14/21）

❌ 改了签名/返回值不 grep 全量引用 → 下游断裂；不 grep 同类实现从零写 → Code Review 出 P1；写完不对照 TDD → 字段名偏离
✅ 改前 grep 同类 pattern 复用 → 改前 grep 全量引用确认 → 改后逐条对照 TDD → 改后涟漪推演（变量可达性+mock 同步）
> 已在 CLAUDE.md 增设独立「代码修改 checklist」。详见 [postmortem-dev-bug-6.md](../postmortems/postmortem-dev-bug-6.md)、[postmortem-dev-bug-11.md](../postmortems/postmortem-dev-bug-11.md)

### DEV-7 测试验证偷懒：pytest 冒充 ST / E2E 不跑 / 旧服务器没重启（含 DEV-15/24）

❌ pytest 全绿就声称"ST 通过"；E2E 脚本写了不当场跑就 commit；代码改了但旧服务器还在跑，测试结果不可信
✅ ST = 真实服务器+真实网络，不是 pytest；E2E 写完必须当场跑看到真实响应；改了 server/*.py → kill 旧进程+重启
> 已在 CLAUDE.md 增设独立「ST 执行前 checklist」。详见 [postmortem-dev-bug-12.md](../postmortems/postmortem-dev-bug-12.md)

### DEV-8 Write 工具调用缺少 content 参数反复失败（⚠️ 五次复犯）

❌ 长文件生成时连续发空 Write 调用（无 content），五次复犯。根因：一次性生成超长 content 导致参数被截断，模型自己感知不到截断发生，所以"记得规则"也没用
✅ ≤100 行正常 Write；>100 行先 Write 前 50 行骨架再 Edit 追加每段 ≤50 行。Write 失败 1 次 → 切 Bash `cat <<'EOF' > file`；Bash 也失败 → 继续拆小段。禁止同一方式连续失败超过 2 次
> 路径 B：五次复犯证明"按文件长度分策略"无效——模型在生成长 content 时参数会被截断，且模型自身无法感知。唯一有效对策是把单次 Write 上限压到 30 行以内，从结构上规避截断。

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

### DEV-16 调研任务串行搜索 → 浪费时间，违反 CLAUDE.md 并行规则

❌ 调研"无人值守开发模式"时，把 4 个独立子主题（质量保障、并行开发、调度机制、架构对比）塞进 1 个 subagent 串行搜索
✅ 搜索关键词超过 2 组时，拆成多个并行 Task agent 分头搜索，最后汇总
> CLAUDE.md 第 72 行明确规定"调研/搜索任务必须并行"。根因：把调研看成"一个问题"没做任务分解。判断标准：搜索关键词 ≥ 2 组 → 拆并行 agent。

### DEV-24 更新文档只改局部不扫全文

❌ 用户说"更新 README"，只改了截图和架构图，没扫描全文 → 特性列表、计划中、测试数字、项目结构、文档链接全部过时
✅ 更新任何文档前先全文扫描，列出所有过时点，一次性全部更新。"更新"= 全面审查一致性，不是只改最明显的一处
> 根因：窄化理解用户意图。判断标准：用户说"更新 X 文件" → 先通读全文对比当前系统状态，再动手。

### DEV-27 写 API 层只关注"能调通"，忽略系统边界防御

❌ Pydantic model 当透传容器不加边界约束（NaN/Infinity 穿透）；service 错误一刀切 400；不看 service 完整签名硬编码调用（漏 status_filter/offset）；`_map_error_status` 只写了"不能/已/不足"三个关键词，漏了"只能" → 返回 400 而非 409（二次复犯）
✅ 写 API 端点时：① 读 service 完整签名透传所有参数 ② 数值字段加 gt/ge/le + 非法值拦截 ③ 错误语义映射正确 HTTP 状态码 ④ **错误映射写完后 grep service 层所有 raise/return error 消息，逐条验证映射覆盖**
> 已在 CLAUDE.md「代码修改 checklist」增设第 5 步「系统边界检查」。二次复犯：映射关键词不全。

### DEV-29 P0/P1 修复列表漏项 + 执行节奏碎片化

❌ Code Review 列了 5 个 P1，只修了 4 个漏掉 P1-5；独立修改逐个做每个停一次；ST 脚本碎片追加 Edit 7-8 次卡在匹配不唯一；独立文件更新串行 6 次来回
✅ P0/P1 列表逐条核销不漏项；多个独立修改一条消息并行发出；新建长文件 Write 主体+最多 1-2 次 Edit 补尾；独立文件更新并行
> 路径 A：门禁 checklist 有"P0/P1 归零"但执行时漏了一条。已在 CLAUDE.md 通用规则新增「并行执行原则」。

### DEV-32 门控表缺视觉序号 → TDD 被误当里程碑起始动作

❌ 用户说"启动 M6 规划"，AI 看到门控表里 AR 列写着 `TDD-M*-xxx.md`，条件反射"先写 TDD"，跳过了 IR 和 SR
✅ 门控表已修复：三行加 ①②③ 序号，AR 行 TDD 旁加括号备注"IR+SR 通过后才写"。流程文档里的产出物命名要带顺序暗示，避免显眼名称被误读为起点
> 根因：门控表 IR/SR 用了 `01-`/`02-` 前缀，AR 直接写 `TDD-M*-xxx.md` 没有序号，视觉上脱离了顺序链。

### DEV-31 网页搜索走 curl 而非浏览器 → SPA 页面拿不到内容白费轮次

❌ 查 OpenRouter 限流文档时用 curl 抓 SPA 页面，拿到的全是空壳 HTML（JS 渲染内容为空），反复换 URL 浪费 4 轮
✅ CLAUDE.md 已有规则「网页浏览优先级：jina.ai → Playwright → WebFetch」。SPA/动态页面必须走 Playwright，curl 只适合静态页面或 API
> 根因：没遵守已有流程规则。判断标准：目标是文档网站 → 大概率 SPA → 直接 Playwright。

### DEV-34 SR 阶段门禁当建议跳过 → 实现与验证脱节

❌ SR 写了"T4 通过后进入阶段 B"，但 pytest 全绿就直接编码；ST 绕开 LLM 只测自动机
✅ SR 阶段门禁是硬性卡点；编码前回 SR 确认"当前阶段、前置 T 是否通过"；ST 对照 SR 验收标准逐条确认
> 根因：把 SR 当"参考"而非"合同"。判断标准：编码前能否在 SR 指出"我在第几阶段、前置 T 已通过"。

### DEV-33 pytest 冒充 ST（DEV-7 复犯）+ P0/P1 归零跳过归因

❌ 任务入口判断"直接实施"→ 跳过 ST checklist → 复用 pytest 模式写 test_m5_e2e.py → 声称"ST 通过"；修完 P1-1 直接宣布"P0/P1 归零"，没有归因（这个 bug 怎么引入的？checklist 需要更新吗？）
✅ ST 脚本必须放 server/e2e_*.py + 真实服务器（现已由 server_utils.managed_server() 自动管理）；P0/P1 归零 = 修复 + 归因（路径 A/B/C/D）+ 判断是否更新 checklist，三步缺一不可
> 根因：把流程步骤当形式，走完就算，没有真正执行每步内容。判断标准：声明"归零"前必须能回答"这个 bug 是怎么引入的"。


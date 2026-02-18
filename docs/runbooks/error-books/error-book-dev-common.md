# 错题本 — 💻 开发者 / 通用开发（前后端共用）

> **记录规则**：本文件只记录跨前后端的通用教训（双终端分工、接口契约、工具调用策略、外部 CLI 集成、Git 流程、Code Review 流程等）。纯前端问题写 `error-book-dev-frontend.md`，纯后端问题写 `error-book-dev-backend.md`。每条控制在 **5 行以内**（❌/✅/一句话根因），详细 checklist 和复盘放 `postmortems/postmortem-dev-bug-N.md`，错题本里只放链接。

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

### DEV-4 复杂功能跳过需求评审

❌ 直接开始写代码，没有 REQ 文档
✅ 新功能先走四方需求评审（阶段1），产出 REQ-XXX.md
> 简单 Bug 可以跳过，复杂功能必须评审。

### DEV-5 实施不遵循 TDD 文档

❌ TDD 定义了接口格式，实施时自己改了字段名
✅ 严格按 TDD 实施，需要改设计先更新 TDD 再改代码
> TDD 是契约，改契约需要走流程。

### DEV-6 修复代码时只看 bug 点，不做影响面分析

❌ 改了变量赋值语义（增量→覆盖），没有检查下游引用是否仍成立，导致死代码、语义矛盾
✅ 修复前 grep 所有引用点，逐个确认改动后语义是否成立；改完后做"涟漪推演"
> 每次修复都改变代码结构，改变本身可能引入新的边界问题。目标是 review 循环 ≤2 轮。

**修复前必做检查清单**:
1. grep 被改变量/函数的所有引用点，逐个确认语义是否仍成立
2. 如果改变了赋值语义（增量→覆盖、必传→可选），追踪所有下游消费者
3. 改完后做"涟漪推演"：这个改动会让哪些下游行为变化？
4. 删参数/改签名时，grep 所有调用方 + 测试中的 assert
5. 不靠隐式假设保安全，用显式代码结构保安全（elif/identity check）

### DEV-7 把 pytest 单元测试当成 ST（系统测试）验证

❌ 被要求"启动 ST 测试"时，直接跑 `pytest tests/`，声称"全绿=验证通过"
✅ ST 测试 = 启动真实服务器 + 调用真实 API + 观察真实行为
> 单元测试全绿只能证明 mock 环境下逻辑正确，不能证明真实环境下端到端流程可用。

**区分清单**:
1. UT（单元测试）: `pytest tests/` — mock 依赖，验证函数逻辑
2. ST（系统测试）: 启动 uvicorn → curl/httpx 调用 API → 检查数据库/WebSocket 广播
3. E2E（端到端测试）: 前后端联调，浏览器/Playwright 驱动完整用户流程

### DEV-8 Write 工具调用缺少 content 参数反复失败（⚠️ 二次复犯）

❌ 长文档生成时犹豫，连续 5 次发空 Write 调用（无 content）。第一次记录后仍未根治，M5 TDD 写入时再次复犯
❌ 根因：思考"写什么内容"和"发出工具调用"脱节——脑子在组织内容，手上发出的调用没带 content
✅ Write 无长度限制，一次性带完整 content 写入；第一次失败后立即停下检查参数
✅ **硬性规则**：Write 调用前，先在脑中确认 content 参数已就绪，没就绪就不发调用。宁可多想 10 秒，不多浪费 5 轮
> 工具调用失败后必须读错误信息、修正参数，不允许盲目重试同一调用。连续 2 次同一错误 → 停下来换思路，绝不允许连续 3 次以上相同失败。

### DEV-9 AR 完成后跳过串讲直接编码

❌ TDD-M3 完成后直接创建编码任务，跳过阶段 3/4/5（串讲 + 测试用例设计）
✅ AR 完成后按 `development-workflow.md` 继续：正向串讲 → 反向串讲 → 测试用例设计 → 才能编码
> CLAUDE.md 工作流原来只写到 AR 门控就断了，已补全完整链路（DEV-9 修复）。

### DEV-10 E2E 测试 fixture 只 create_all 不先 drop_all → UNIQUE 冲突

❌ `setup_db` 用 `Base.metadata.create_all` 但不先清理，生产 DB 已有数据时 seed 插入冲突
✅ fixture 先 `drop_all` 再 `create_all`，保证每个测试从空表开始
> 测试隔离是基本功。create_all 对已存在的表是 no-op，不会清数据。

### DEV-11 前后端字段对齐靠目测 → 运行时才发现不匹配

❌ 前端 types.ts 凭记忆写字段，不逐字段比对后端 schema
✅ 写完 types.ts 后逐字段比对：字段名、类型、可选性、枚举值，列表格确认
> 字段名差一个字母 = 运行时 undefined。M3 对齐验证 checklist：Job↔JobOut、ShopItem↔ItemOut、WsSystemEvent↔broadcast payload。

### DEV-13 用户说"用 CLI"，仍然自行绕路直接打 REST API

❌ 用户明确说"用 gemini cli"，脚本里还是用 fetch/undici 直接调 REST endpoint
✅ "用 CLI"= `gemini` subprocess（stdin pipe）是唯一路径；CLI 不支持的功能先问用户，不自行降级
❌ CLI 出现 auth/quota 错误时，转身改用 API key 打 REST
✅ CLI 报错 → 报错给用户，不绕路；quota 耗尽 → 明确告知，不再尝试 REST fallback
❌ 不指定 `-m`，CLI 默认用 Pro → quota 很快耗尽
✅ 明确指定模型：代码审查用 `gemini-2.5-flash-lite`（1000 RPD），设计生成/视觉审查用 `gemini-2.5-flash`（250 RPD），Pro 留给用户手动交互
> 根因：把"调用 Gemini"分成了两条路，CLI 遇阻就滑向 REST。用户指定的工具 = 硬约束，不是"优先项"。

### DEV-12 外部 CLI 集成：跳过环境探针 + 误判错误信息 → 大量无效轮次

❌ 直接写脚本 → 遇到 PATH/代理/认证/quota 等问题逐个补救，共 25+ 轮
✅ 集成外部 CLI 前先做 4 步探针：① which cli ② 检查 HTTPS_PROXY ③ 读认证配置 ④ 手动测一条命令
❌ Gemini 429 `limit:0` 误判为"每日用尽" → 绕去 OAuth/resume 等方案
✅ 429 有 retryDelay（秒数）= RPM 速率限制，等待即可；无 retryDelay = 真正用尽
❌ 用默认模型 gemini-2.5-pro（5 RPM, 100 RPD），开发测试频繁调用必然触限
✅ 脚本优先用 gemini-2.5-flash（10 RPM, 250 RPD）或 flash-lite（1000 RPD）
❌ "把X删掉" → 删掉所有相关存储；用户意图可能只是"不要明文存"
✅ 涉及"删除"的指令先确认范围：删功能 vs 删某个存储位置
> 详见 [postmortem-dev-bug-10.md](../postmortems/postmortem-dev-bug-10.md)

### DEV-14 新功能编码不复用已有 pattern → Code Review 出 P1/P2

❌ 写 `_execute_chats` 时用串行 `for + await sleep`，项目里已有并行 `create_task` 模式（`hourly_wakeup_loop`）
❌ 写 SYSTEM_PROMPT 时擅自偏离 TDD（checkin params 加了 job_id），没走设计变更
❌ try/except 中引用变量未做防御性初始化，异常路径可能 NameError
❌ 写完代码直接提交 Review，没有逐条对照 TDD 自查
✅ 写新函数前 grep 同类实现，复用项目已有 pattern
✅ 写完后逐条对照 TDD 自查：签名、事件格式、prompt 内容、容错场景
✅ 每个 except 分支走一遍变量可达性分析
✅ 不擅自偏离 TDD，改进想法先更新设计文档再改代码

**编码前自查清单（新增）**:
1. grep 同类功能的已有实现，确认项目 pattern（延迟发送、广播、session 管理）
2. 对照 TDD 逐项检查：函数签名、消息格式、prompt 内容、容错边界
3. 每个 try/except 块检查异常路径的变量可达性
4. 不偏离 TDD，需要改设计先更新文档
5. 替换组件/模块时，grep 旧名称的所有引用，逐个清除（文件、import、类型、mock 数据、CSS）
6. 对照 TDD 的用户故事编号逐个勾选，不要凭感觉"差不多了"
7. 生成 id/key 时考虑并发和碰撞：避免 Date.now() 裸用，优先用自增计数器或负数隔离
8. 时间相关 UI 考虑"用户停留 30 分钟后"的表现

> 根因：只关注"功能正确"忽略"模式一致"和"文档一致"。详见 [postmortem-dev-bug-11.md](../postmortems/postmortem-dev-bug-11.md)

### DEV-15 写了 E2E 脚本不当场跑 → 假绿交差

❌ 写了 `e2e_m4.py`（真实 LLM E2E 脚本），没启动服务器跑一遍就 commit + push，声称"E2E 完成"
❌ `test_e2e_autonomy.py` 全部 mock LLM，本质是集成测试，却标记为"E2E 9/9 passed"
❌ 真正启动服务器后发现：端点 404（旧代码）、Agent 为空（无 seed）、LLM 全返回 rest（prompt/模型问题）
✅ E2E 脚本写完必须当场启动服务器跑一遍，看到真实 LLM 响应才算验证
✅ mock 测试明确标记为"集成测试"，不混淆为 E2E
✅ 真实 E2E 脚本必须包含 seed 逻辑（创建 Agent/Job/Item），不依赖外部手动准备

**E2E 验证必做清单**:
1. 启动真实服务器（确认最新代码，清 pycache）
2. 确认数据 seed（Agent/Job/Item 存在）
3. 确认外部依赖可达（LLM API + 代理）
4. 跑脚本看到真实 LLM 响应（不是 mock）
5. 验证状态变化（DB credits 变了、WebSocket 收到事件）
6. 以上全通过后才能 commit 并声称"E2E 通过"

> 根因：被 mock 测试的绿色结果蒙蔽，把"写了脚本"等同于"验证通过"。DEV-7 说过 UT≠ST，这次是 mock≠E2E 的同类错误。

### DEV-16 调研任务串行搜索 → 浪费时间，违反 CLAUDE.md 并行规则

❌ 调研"无人值守开发模式"时，把 4 个独立子主题（质量保障、并行开发、调度机制、架构对比）塞进 1 个 subagent 串行搜索
✅ 搜索关键词超过 2 组时，拆成多个并行 Task agent 分头搜索，最后汇总
> CLAUDE.md 第 72 行明确规定"调研/搜索任务必须并行"。根因：把调研看成"一个问题"没做任务分解。判断标准：搜索关键词 ≥ 2 组 → 拆并行 agent。

### DEV-17 拿到实施方案直接编码，跳过 PM 评审 + 用户确认

❌ M5 实施方案包含多个待确认设计决策（资源归属模式、交易市场范围、生产频率），直接派 agent 开干
❌ 中途用户连续提出 3 次变更（tick→天、加交易市场、公共池→个人资源），每次都要中断 agent 返工
❌ 并行拆分也有问题：第一轮只拆 2 个 agent（前端/后端），没按功能模块拆（记忆/城市），浪费并行度
✅ 拿到方案后先提取所有待确认点，逐个提交用户决策，全部确认后再编码
✅ 按功能模块拆并行 agent（独立路径数 = agent 数），不按技术层拆
> 根因：DEV-4（跳过评审）+ DEV-9（跳过串讲）的复合重犯。方案看起来"很完整"就产生了"可以直接干"的错觉。教训：方案越完整越要逐项确认，因为完整方案里隐含的假设更多。

### DEV-20 排查外部进程问题时串行试错 + 不验证前置假设 → 每轮等超时白耗时间

❌ 排查 claude-mem worker 子进程超时时，一次只验证一个假设（先改模型名 → 等 3 分钟 → 再查代理 → 等 3 分钟 → 再发现改错文件 → 又等 3 分钟）
❌ 改了配置文件没确认 worker 实际读的是哪个路径（`~/.claude-mem/settings.json` vs `E:/claude-mem/settings.json`，两份配置）
❌ 没先检查 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量就去翻 minified 源码找函数实现
✅ 排查外部进程/CLI 集成问题时，先做 **环境全景扫描**（5 分钟内完成）：
  1. `env | grep -i proxy` — 检查所有代理变量
  2. `curl --noproxy "*"` — 验证直连是否通
  3. 确认配置文件实际路径（grep 源码中的 hardcoded path）
  4. 确认进程实际读的是哪份配置（看日志或 strace）
✅ 多个可能原因时 **并行验证**，不串行等超时：同时测模型名 + 测网络连通性 + 确认配置路径
✅ 改了配置后 **立即验证生效**：读回文件确认内容 + 检查进程是否读的同一份文件
> 根因：DEV-12（外部 CLI 集成跳过环境探针）的同类错误。面对"子进程超时无响应"的症状，没有系统性列出所有可能原因再并行排除，而是顺着一条线走到黑，每次撞墙等 3 分钟才换方向。

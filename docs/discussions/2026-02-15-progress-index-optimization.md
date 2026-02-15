# 进度索引优化 — 协作讨论详细记录

**日期**：2026-02-15
**议题**：优化"今天做了什么"的查询效率
**参与者**：人类替身PM、信息架构师、维护成本分析师、工具集成专家、架构师
**流程**：协作融合（2轮）
**决策结果**：采用融合方案（claude-progress.txt 顶部 + Git commit 引用）

---

## 背景和需求

### 用户痛点

用户想快速了解"今天做了什么"，但信息分散在多个文件中：
- `claude-progress.txt`（只有大里程碑）
- `server/progress.md`（后端细节）
- `docs/discussions.md`（讨论索引）
- `git log`（提交记录）

总结一天的工作需要读取多个文件，慢且容易遗漏。

### 现有体系

根据 `docs/runbooks/layered-progress-guide.md`：
- **小进展**（单个API/组件/测试）→ `server/progress.md` 或 `web/progress.md`
- **大里程碑**（M1/M2完成、联调、架构决策）→ `claude-progress.txt`
- **讨论记录** → `docs/discussions/` + 索引

### 待评估方案

- **方案A**：增加 `daily-work-log.md`（每日工作日志）
- **方案B**：`claude-progress.txt` 顶部增加"最近7天"章节
- **方案C**：利用 git commit（每天总结性 commit）
- **方案D**：memory-keeper MCP journal 功能

---

## 第1轮：多角度初步方案

### 人类替身 PM 视角

**推荐方案**：方案 B（claude-progress.txt 顶部增加"最近7天"）

**核心优势**：
1. **零学习成本**：用户已经习惯打开 `claude-progress.txt` 看进度，不需要记住新文件名或新命令
2. **自动聚合，无需手动维护**：每次更新大里程碑时，自动把最近 7 天的条目提到顶部
3. **信息密度刚好**：7 天窗口覆盖一周工作，既能快速回顾，又不会信息过载
4. **与现有分层进度管理无缝衔接**：小进展还是记 `server/progress.md`，大里程碑同步到 `claude-progress.txt` 时自动进入"最近 7 天"

**不足之处**：
- 依赖 AI 自觉更新，如果忘记同步会漏信息
- git log 信息丢失（但用户痛点不是"看 git 历史"）

**请教问题**：
- 技术实现：如何自动维护"最近 7 天"章节？
- 信息粒度：7 天窗口里应该显示什么级别的信息？
- 与 memory-keeper 的关系：能否作为补充？

### 工具集成专家视角

**推荐方案**：方案 C（Git commit 总结）+ 可选 memory-keeper 补充

**核心优势**：
1. **零学习成本，已在用**：Git commit 已经是习惯，今天 8 个 commit，信息完整
2. **信息密度最高**：Commit 自带时间戳、作者、变更文件列表，比手写日志更准确
3. **工具链成熟稳定**：Git 是基础设施，无依赖风险，支持多维度查询
4. **可扩展性强**：需要更详细？加 `--stat`；需要分类？用 `--grep`

**不足之处**：
- 非代码决策难追踪（如"讨论后决定不做某功能"）
- 需要 commit 规范（当前项目已做得很好）
- 跨天查询需要计算（但可以写成 shell alias）

**请教问题**：
- 用户真实需求是"快速回顾"还是"向他人汇报"？
- memory-keeper MCP 是否已在其他场景使用？
- 是否愿意保持规范的 commit message 格式？

**实施建议**：
```bash
# 方案1：命令行查询（最轻量）
git log --since="today" --pretty=format:"- %s"

# 方案2：Shell alias（一次配置，长期使用）
alias today="git log --since='today' --oneline"
alias week="git log --since='7 days ago' --oneline"
```

### 维护成本分析师视角

**推荐方案**：方案 B + D 组合（claude-progress.txt 顶部"最近7天" + memory-keeper journal 辅助）

**核心优势**：
1. **零新文件，零心智负担**：不引入新文件，开发者已经习惯更新 `claude-progress.txt`
2. **最不容易被遗忘**：`claude-progress.txt` 是 CLAUDE.md 强制加载的文件，每次会话必读，"最近7天"在顶部，视觉优先级最高
3. **自动过期，无堆积负担**：7天滚动窗口，超过7天的自动删除
4. **memory-keeper 作为保险**：如果忘记更新，可以用 `context_timeline` 回溯

**不足之处**：
- 需要手动维护，无法完全自动化
- 需要定义"每日摘要"的格式
- 依赖纪律，连续多天不更新会失真

**请教问题**：
- claude-progress.txt 顶部增加章节是否会破坏分层逻辑？
- "每完成一个 Phase，顺手在顶部加一行摘要"的习惯容易养成吗？
- 用户希望看到"任务级摘要"还是"价值级摘要"？
- Git commit 总结是否有价值？

### 信息架构师视角

**推荐方案**：时间轴聚合视图 + 分层存储不变

**核心思路**：在 `claude-progress.txt` 顶部增加"最近活动"区块（滚动窗口，保留最近 7 天），通过脚本自动聚合生成。

**示例格式**：
```markdown
## 最近活动（自动生成，最近7天）

### 2026-02-16
- [后端] M2-2 记忆读写服务完成 (server/progress.md#L119)
- [后端] M2-6 发言扣费集成完成 (server/progress.md#L120)
- [讨论] 进度索引优化方案评估 (docs/discussions.md)
- [提交] 3 commits: feat(memory), test(economy), docs(progress)

### 2026-02-15
- [里程碑] M2 Phase 1 完成 (claude-progress.txt#L110)
- [竞品] MaiBot 分析完成 (claude-progress.txt#L67)
- [提交] 2 commits: feat(vector-store), docs(maibot)
```

**核心优势**：
1. **单一入口，零认知负担**：用户只需读 `claude-progress.txt` 顶部，3 秒内看到"今天做了什么"
2. **信息不重复，只有索引**："最近活动"区块只存指针（文件路径 + 行号），不复制原文
3. **自动化生成，零维护成本**：通过脚本扫描 git log + 进度文件的时间戳，自动生成聚合视图

**不足之处**：
- 依赖脚本实现，增加工具链复杂度
- 跨文件跳转成本，不如"一站式阅读"
- git log 噪音过滤，需要智能过滤 WIP commits

**请教问题**：
- 用户查询"今天做了什么"的典型场景是快速扫一眼（30秒）还是深入了解（5分钟）？
- 脚本实现的可行性？用 Python 还是 memory-keeper MCP 的 timeline API？
- 用户想要决策结论还是讨论过程？

---

## 第2轮：协作融合

### 工具集成专家（改进方案）

**核心调整**：从"纯 Git 查询"升级为"Git + claude-progress.txt 自动聚合视图"

**改进点**：
1. 采纳信息架构师的"单一入口"理念：在 `claude-progress.txt` 顶部增加"最近7天活动"区块
2. 采纳维护成本分析师的"自动过期"机制：每次更新时自动刷新，超过7天自动移出
3. 保留 Git 作为数据源：不重复记录，Git commit 是唯一真相来源

**实施方案**（最小化开发成本）：
```bash
#!/bin/bash
# update-progress.sh - 在每次 commit 后自动运行（20行）
git log --since="7 days ago" --pretty=format:"- %s" \
  | awk '{print "### " $1 "\n" $0}' \
  | sed '1i## 最近7天活动（自动生成，勿手动编辑）' \
  > /tmp/recent.txt

# 替换 claude-progress.txt 顶部区块
sed -i '/^## 最近7天活动/,/^## 里程碑记录/d' claude-progress.txt
cat /tmp/recent.txt claude-progress.txt > /tmp/new-progress.txt
mv /tmp/new-progress.txt claude-progress.txt
```

**对其他方案的建议**：
- **给人类替身 PM**：同意"顶部增加最近7天"，但建议改为"自动生成"而非"手动维护"
- **给维护成本分析师**：同意"自动过期"机制，但不建议引入 memory-keeper（当前项目未使用，增加工具依赖）
- **给信息架构师**：完全同意"单一入口 + 自动化生成"，建议脚本触发时机改为"git commit hook"

**共识点**：
- ✅ 位置：claude-progress.txt 顶部
- ✅ 时间范围：最近7天
- ✅ 零新增文件
- ✅ 自动过期

**分歧点**：
- 数据来源：Git commit（自动）vs 手动记录（更灵活）
- 是否引入 memory-keeper：反对（增加工具复杂度）

**最终建议**：
- Phase 1（立即可做）：手动在顶部增加"最近7天"区块
- Phase 2（可选）：开发 `update-progress.sh` + git hook

### 维护成本分析师（改进方案）

**核心改变**：接受工具专家的 Git Commit 方案作为主力，因为它是唯一不需要额外维护的方案。

**具体实施**：
1. **Git Commit 作为主力记录**：每完成一个 Phase/任务，commit message 格式规范
2. **claude-progress.txt 顶部"最近7天"作为快速索引**：自动生成（采纳信息架构师建议）
3. **放弃 memory-keeper journal**：Git commit 已经是"自动化保险"

**对其他方案的建议**：
- **给工具专家**：方案最可持续，但需要补充"非代码决策"的记录方式（用 `docs:` commit）
- **给信息架构师**："自动聚合视图"思路好，但简化为"从 git log 提取 + 填充到顶部"（≤20行脚本）
- **给人类替身 PM**："零学习成本"判断准确，但手动维护不可持续，建议接受 Git Commit 为主力

**最终立场**：长期最可持续的是 Git Commit，claude-progress.txt 顶部应该自动生成。

### 信息架构师（改进方案）

**改进后的方案**：claude-progress.txt 顶部"最近7天" + Git 提交摘要

**示例格式**：
```markdown
## 最近7天活动（自动过期，每次更新时清理 >7天条目）

### 2026-02-16
- **[里程碑]** M2-8 悬赏任务API完成 → 详见 server/progress.md#L125
- **[提交]** 3 commits: `feat(bounty)`, `test(economy)`, `docs(api-contract)`
- **[讨论]** 进度索引优化 → docs/discussions.md

### 2026-02-15
- **[里程碑]** M2 Phase 1 完成 → 详见下方"大里程碑"
- **[提交]** 2 commits: `feat(vector-store)`, `docs(maibot)`
```

**关键改进**：
1. **放弃脚本自动生成**：Agent 手动维护，但有明确规则（每次更新时删除 >7天条目）
2. **Git 提交作为主要信息源**：commit message 本身就是最佳摘要，只需在"最近7天"区块引用
3. **分层索引**：小进展只记 commit，大里程碑才写详细条目

**对其他方案的建议**：
- **给人类替身 PM**：补充"自动过期规则"——Agent 每次更新时检查并删除超过 7 天的条目
- **给工具专家**：Git commit 是最低成本方案，但建议在顶部显式引用，不让用户自己跑 `git log`
- **给维护成本分析师**：memory-keeper journal 作为可选增强，但不应作为主方案（外部工具依赖风险）

**共识点**：
- ✅ 位置：claude-progress.txt 顶部
- ✅ 时间窗口：最近 7 天
- ✅ 零新文件
- ✅ 信息密度：只记索引/摘要，不复制原文

**分歧点**：
- 维护方式：手动 + 明确规则 vs 脚本自动生成
- 信息来源优先级：Git commit vs 文件内容

### 人类替身 PM（改进方案）

**改进方案**：claude-progress.txt 顶部"最近7天" + Git commit 作为主力 + memory-keeper 作为可选保险

**核心改进**：降低 claude-progress.txt 的更新频率，改为：
1. **Git commit 作为日常记录主力**：每天工作结束时，AI 主动建议用户做一次总结性 commit
2. **claude-progress.txt 只记大里程碑**：顶部"最近7天"章节自动聚合最近的大里程碑条目
3. **memory-keeper journal 作为可选保险**：AI 自动记录关键决策

**对其他方案的建议**：
- **给工具专家**：Git commit 最务实，但建议增加"AI 主动提醒"机制（帮用户生成 commit message）
- **给信息架构师**："自动聚合视图"思路好，但"依赖脚本"可能过度设计，建议简化为"AI 手动维护"

**共识点**：
- ✅ 不新增独立的 daily-work-log.md
- ✅ claude-progress.txt 顶部需要"最近活动"视图
- ✅ memory-keeper 可以作为辅助工具，但不是主力

**分歧点**：
- 日常记录的主力：Git commit vs claude-progress.txt
- "最近7天"章节的更新频率：每天更新 vs 只在大里程碑时更新
- 是否需要脚本自动化

**最终立场**：用户是单人项目，优先选择"已经在用的工具"（Git）而不是"新增维护负担"。

---

## 架构师汇总

### 关键共识点（4/4 专家一致同意）

✅ **位置**：claude-progress.txt 顶部
✅ **时间范围**：最近 7 天滚动窗口
✅ **零新文件**：不创建 daily-work-log.md
✅ **自动过期**：超过 7 天的条目自动移除
✅ **信息不重复**：只存索引/摘要，不复制原文

### 核心分歧点

**分歧1：数据来源**
- **Git commit 派**（工具专家 + 维护成本分析师）：Git 是唯一真相来源，已在用，零额外成本
- **手动维护派**（人类替身 PM + 信息架构师）：手动更灵活，能记录非代码决策

**分歧2：自动化程度**
- **脚本自动生成**（信息架构师 + 工具专家）：20 行脚本 + git hook，彻底解放手动维护
- **手动维护**（人类替身 PM + 维护成本分析师）：先手动试运行，有痛点再自动化

### 最终推荐方案（融合方案）

**Phase 1：立即可做（零开发成本）**

在 `claude-progress.txt` 顶部增加：

```markdown
## 最近 7 天活动

### 2026-02-16
- **[里程碑]** M2 Phase 2 完成（记忆服务+扣费+定时任务）
- **[提交]** 3 commits: feat(memory), feat(economy), test(scheduler)

### 2026-02-15
- **[里程碑]** M2 Phase 1 完成（向量存储+经济服务+用量追踪）
- **[竞品]** MaiBot 分析完成，M2 纳入 3 项特性
- **[提交]** 2 commits: feat(vector-store), docs(maibot)

---

## 当前状态
...
```

**维护规则**：
1. 每次更新大里程碑时，在顶部增加一条（≤50 字）
2. 引用最近的 git commits（`git log --oneline -5`）
3. 每次更新时删除超过 7 天的条目

**Phase 2：可选自动化（如果 Phase 1 有痛点）**

```bash
# update-recent.sh（20 行）
git log --since="7 days ago" --pretty=format:"- %s" \
  | sed '1i## 最近 7 天活动\n' \
  > /tmp/recent.txt
# 替换 claude-progress.txt 顶部区块
```

### 方案对比表

| 维度 | Git Commit 查询 | claude-progress.txt 顶部 | 融合方案 |
|------|----------------|------------------------|---------|
| 查询速度 | 10秒（需切终端） | 3秒（打开文件） | 3秒 ✅ |
| 维护成本 | 0（已在用） | 低（顺手加一行） | 低 ✅ |
| 信息完整性 | 高（代码变更） | 中（只记大事） | 高 ✅ |
| 非代码决策 | 差（需配合文档） | 好（可手动补充） | 好 ✅ |
| 工具依赖 | Git | 无 | Git（可选） |
| 学习成本 | 0 | 0 | 0 ✅ |

### 实施建议

**立即执行**：
1. 在 `claude-progress.txt` 顶部增加"## 最近 7 天活动"章节
2. 把今天的工作（M2 Phase 1 完成 + MaiBot 分析）写进去
3. 试运行 1-2 周

**观察指标**：
- 是否真的每次都记得更新？
- 查询"今天做了什么"的时间是否 <30 秒？
- 是否出现信息遗漏？

**如果有痛点**：
- 遗忘率高 → 开发 git hook 自动生成
- 信息不够详细 → 增加 memory-keeper journal 补充非代码决策

### 不推荐的方案

❌ **daily-work-log.md**：信息重复，易不同步
❌ **纯 Git 查询**：需要切终端，不够直观
❌ **立即开发脚本**：过度设计，先验证需求

---

## 决策结论

**采用融合方案**：
- **Phase 1**：手动在 claude-progress.txt 顶部维护"最近 7 天活动"章节
- **Phase 2**：如果 Phase 1 有痛点，再开发自动化脚本

**符合原则**：
- ✅ 务实成本控制：先手动验证需求，再投入开发
- ✅ 对话是临时的，文件是持久的：信息落盘到 claude-progress.txt
- ✅ 零学习成本：复用现有文件和习惯

---

## 下一步行动

1. **立即执行**：在 `claude-progress.txt` 顶部增加"最近 7 天活动"章节
2. **更新索引**：在 `docs/discussions.md` 中增加本次讨论的条目
3. **试运行**：观察 1-2 周，收集反馈
4. **可选优化**：如果有痛点，开发自动化脚本

# 完整开发流程（四方协作）

> 从需求到上线的完整开发流程。文档模板见 [doc-templates.md](../templates/doc-templates.md)。

---

## 流程总览

```
需求输入
  ↓
阶段 1：四方需求评审（Architect + Tech Lead + QA Lead + Developer）
  ↓
阶段 2：技术设计（Developer/Tech Lead 编写 spec）
  ↓
阶段 2.5：UI 设计稿（Gemini 生成）[仅含前端 UI 的功能]
  ↓
阶段 3：正向串讲（Developer → QA Lead）[可选]
  ↓
阶段 4：反向串讲（QA Lead → Developer）[可选]
  ↓
阶段 5：测试用例设计（QA Lead）
  ↓
阶段 6：开发实施（Claude Code 按设计稿写代码）
  ↓
阶段 6.5：UI 美学验收（Gemini 截图审查）[仅含前端 UI 的功能]
  ↓ ← 未通过则回到阶段 6 修复，再次验收
阶段 7：集成测试（QA Lead 验证 + Developer 修复）
  ↓
阶段 8：上线评审（四方确认）
```

**文档粒度**：根据复杂度调整（轻量级 vs 详细级），模板见 [doc-templates.md](../templates/doc-templates.md)

**串讲环节**：可选
- 简单修改/Bug 修复：可跳过
- 复杂功能/新模块：必须串讲

---

## 阶段 1：四方需求评审

**目标**：从四个视角评估需求，识别风险，达成共识。

**参与**：Architect（架构）+ Tech Lead（技术）+ QA Lead（测试）+ Developer（实施）

**Agent Team 实现**：
- 各 Agent 独立评估后汇总到共享任务列表
- Architect 综合四方意见，整理需求澄清文档
- 如有重大分歧，发起协作讨论（见 [debate-workflow.md](debate-workflow.md)）

**产出**：`docs/specs/SPEC-XXX-功能名/spec.md`（需求概述 + 四方评审结论 + Go/No-Go）

**检查点**：
- [ ] spec 文件已创建，四方评审意见已记录
- [ ] Go/No-Go 决策已做出
- [ ] 如有分歧已通过讨论解决

---

## 阶段 2：技术设计

**目标**：在 spec 文件中补充技术设计部分（架构、接口、数据库、流程）。

**负责**：Developer（主责）→ Architect（审核）

**实现**：
1. 读取 `docs/specs/SPEC-XXX/spec.md` 的需求部分
2. 在同一文件中补充技术设计（架构图、模块划分、接口定义、数据库设计、关键流程、风险应对）
3. Architect 审核通过后更新状态

**检查点**：
- [ ] spec 文件包含完整技术设计
- [ ] Architect 审核通过

---

## 阶段 2.5：UI 设计稿（Gemini 生成）

**触发条件**：功能包含新的前端 UI 组件或页面。纯后端/API 功能跳过此阶段。

**目标**：在写代码前，让 Gemini 作为 UI 设计师产出设计规格，Claude Code 按规格实现，保证视觉质量。

**执行**：
```bash
# 输入功能描述，Gemini 输出设计稿
VAULT_MASTER_KEY="your-key" node scripts/gemini-design.mjs "功能描述"
```

**输出**：`docs/specs/_ui-designs/YYYY-MM-DD-功能名.md`，包含：
- 组件结构树
- 布局规格（尺寸、flex/grid、间距）
- 视觉规格（CSS 变量、圆角、阴影）
- 交互状态（hover、empty、loading）
- 关键 CSS 片段
- 验收标准（供阶段 6.5 使用）

**检查点**：
- [ ] 设计稿已生成并保存到 `docs/specs/_ui-designs/`
- [ ] 设计稿包含明确的验收标准（至少 5 条）
- [ ] Claude Code（Developer）已阅读设计稿，理解要求

---

## 阶段 3：正向串讲（Developer → QA Lead）

**目标**：Developer 向 QA Lead 讲解设计，确保 QA 理解实现方案。

**何时执行**：复杂功能必须，简单修改可跳过。

**产出**：
- Developer 更新 spec（补充 QA 提出的遗漏点）
- QA Lead 输出测试场景列表（初稿）

**检查点**：
- [ ] QA Lead 理解了设计
- [ ] spec 已补充遗漏点

---

## 阶段 4：反向串讲（QA Lead → Developer）

**目标**：QA Lead 用自己的话复述设计，确认双方理解一致。

**何时执行**：与正向串讲同步，复杂功能必须。

**产出**：
- 测试场景列表（最终版）
- spec 标记为"已串讲确认"

**检查点**：
- [ ] Developer 确认 QA 理解正确
- [ ] 测试场景列表已最终确认

---

## 阶段 5：测试用例设计

**目标**：QA Lead 编写详细测试用例（Given-When-Then 格式）。

**负责**：QA Lead

**产出**：`docs/tests/TEST-XXX.md`

**检查点**：
- [ ] 覆盖正常流程、异常流程、边界条件
- [ ] 测试数据和预期结果明确

---

## 阶段 6：开发实施

**目标**：前后端并行实施。

**分工**：
- 后端终端：只改 `server/`，遵循 spec 架构约束
- 前端终端：只改 `web/`，遵循 `docs/api-contract.md` 接口定义
- 每完成一个模块，编写单元测试
- 小进展记 `server/progress.md` 或 `web/progress.md`

**检查点**：
- [ ] 代码已实现，单元测试通过
- [ ] 自测通过，代码已提交
- [ ] 进度已更新

---

## 阶段 6.5：UI 美学验收（Gemini 截图审查）

**触发条件**：阶段 2.5 已执行（即本功能有前端 UI）。

**目标**：Gemini Vision 对照设计稿验收实际界面，确保美学质量达标后才进入集成测试。

**执行**：
```bash
# 先确保开发服务器运行中（npm run dev）
# 基础审查（无设计稿对比）
VAULT_MASTER_KEY="your-key" node scripts/gemini-review.mjs

# 对照设计稿审查（推荐）
VAULT_MASTER_KEY="your-key" node scripts/gemini-review.mjs \
  --url http://localhost:5173 \
  --design docs/specs/_ui-designs/YYYY-MM-DD-功能名.md
```

**通过标准**：综合评分 ≥ 7/10 且无 P0 问题

**循环**：
```
Gemini 审查 → FAIL → Claude Code 修复 → 重新审查 → 直到 PASS
```

**产出**：`docs/specs/_ui-reviews/YYYY-MM-DD-HH-mm-ss.md`

**检查点**：
- [ ] Gemini 审查结论为 PASS
- [ ] 审查报告已保存
- [ ] 所有 P0 问题已修复

---

## 阶段 7：集成测试

**目标**：QA Lead 按测试用例验证，Developer 修复 Bug。

**循环**：QA 测试 → 报告失败 → Developer 修复 → QA 重测 → 直到全部通过

**产出**：`docs/tests/REPORT-XXX.md`

**检查点**：
- [ ] 所有测试用例已执行
- [ ] 阻塞 Bug 已修复并重测通过
- [ ] 测试报告已输出

---

## 阶段 8：上线评审

**目标**：四方最终确认功能可以上线。

**实现**：
1. 确认测试报告全部通过
2. 确认代码已提交、文档已更新
3. 输出上线总结 `docs/releases/RELEASE-XXX.md`
4. 更新 `claude-progress.txt`（里程碑完成）

**检查点**：
- [ ] 四方确认完成
- [ ] 进度文件已更新

---

## 效率规则

1. **不回读自己刚写的文档** — 同一会话中刚产出的 IR/SR/PLAN 内容直接引用，不从磁盘重新加载
2. **并行读文件** — 需要读多个外部代码文件时，一次并行读完，不分批串行
3. **普通文本文档用便宜模型** — AR/TDD 等纯文本文档用子 task + haiku/sonnet 写，不占用 opus 上下文
4. **工具调用失败立即修正** — 读错误信息，修正参数，不盲目重试同一调用
5. **外部进程/CLI 排查先做环境全景扫描** — 排查子进程超时、连接失败等问题时，先花 5 分钟并行验证：① 代理变量（`env | grep -i proxy`）② 直连测试（`curl --noproxy "*"`）③ 配置文件实际路径（grep hardcoded path）④ 进程读的是哪份配置。多个假设并行验证，不串行等超时（参见 DEV-20）

## 流程适配规则

| 场景 | 可省略阶段 | 说明 |
|------|-----------|------|
| 简单 Bug 修复 | 1、3、4、8 | 直接写设计 → 测试 → 实施 → 测试 |
| 单文件小改动 | 1、2、3、4、5、8 | 直接实施 → 自测 |
| 紧急热修复 | 3、4 | 省略串讲，但必须有测试 |
| 文档更新 | 全部省略 | 直接修改，无需流程 |

---

## 版本
v1.1 - 2025-07-09（路径更新为 specs/，模板拆分到 doc-templates.md）

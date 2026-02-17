#!/usr/bin/env node
/**
 * gemini-review.mjs
 * 阶段 6.5：UI 美学验收
 *
 * 用法：
 *   node scripts/gemini-review.mjs                          # 截图 localhost:5173
 *   node scripts/gemini-review.mjs --url http://localhost:5173/some-page
 *   node scripts/gemini-review.mjs --design docs/specs/_ui-designs/xxx.md
 *   node scripts/gemini-review.mjs --code-only              # 只审查代码，不截图
 *
 * 输出：控制台报告 + docs/specs/_ui-reviews/xxx.md
 * 退出码：0 = 通过，1 = 未通过
 *
 * 注意：所有 Gemini 调用统一走 gemini CLI subprocess（stdin pipe / -f 附件）
 *       不使用 REST API 直接调用。
 */

import { readFile, writeFile, mkdir } from 'fs/promises';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { createDecipheriv, scryptSync } from 'crypto';
import { existsSync } from 'fs';
import { execSync, spawnSync } from 'child_process';

// ── 读取 Vault Key ──────────────────────────────────────────────
async function getKeyFromVault(keyName) {
  const vaultPath = join(homedir(), '.vault', 'passwords.json');
  if (!existsSync(vaultPath)) return null;
  const data = JSON.parse(await readFile(vaultPath, 'utf-8'));
  const entry = data[keyName];
  if (!entry) return null;

  const masterKey = process.env.VAULT_MASTER_KEY;
  if (!masterKey) throw new Error('VAULT_MASTER_KEY not set');

  const key = scryptSync(masterKey, Buffer.from(entry.password.salt, 'base64'), 32);
  const d = createDecipheriv('aes-256-gcm', key, Buffer.from(entry.password.iv, 'base64'));
  d.setAuthTag(Buffer.from(entry.password.authTag, 'base64'));
  return d.update(entry.password.encrypted, 'base64', 'utf8') + d.final('utf8');
}

// ── 调用 Gemini CLI（文本，stdin pipe）──────────────────────────
function callGeminiText(apiKey, prompt) {
  const env = { ...process.env };
  if (apiKey) env.GEMINI_API_KEY = apiKey;
  const r = spawnSync('gemini', ['-m', 'gemini-2.5-flash-lite'], {
    input: prompt,
    encoding: 'utf-8',
    timeout: 180_000,
    shell: true,
    env,
  });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(r.stderr || `gemini exit ${r.status}`);
  return r.stdout.split('\n')
    .filter(l => !l.includes('DeprecationWarning') && !l.includes('punycode')
              && !l.includes('Hook registry') && !l.includes('initialized'))
    .join('\n').trim();
}

// ── 调用 Gemini CLI（图片 + 文本，-f 附件）──────────────────────
function callGeminiVision(apiKey, screenshotPath, prompt) {
  const env = { ...process.env };
  if (apiKey) env.GEMINI_API_KEY = apiKey;
  // gemini CLI: gemini -m <model> -f <image> "<prompt>"
  const r = spawnSync('gemini', ['-m', 'gemini-2.5-flash', '-f', screenshotPath, prompt], {
    encoding: 'utf-8',
    timeout: 180_000,
    shell: true,
    env,
  });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(r.stderr || `gemini exit ${r.status}`);
  return r.stdout.split('\n')
    .filter(l => !l.includes('DeprecationWarning') && !l.includes('punycode')
              && !l.includes('Hook registry') && !l.includes('initialized'))
    .join('\n').trim();
}

// ── 用 Playwright 截图 ──────────────────────────────────────────
async function takeScreenshot(url) {
  const outPath = join(process.cwd(), '.playwright-mcp', `ui-review-${Date.now()}.png`);
  await mkdir(dirname(outPath), { recursive: true });

  const script = `
const { chromium } = require('playwright');
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('${url}', { waitUntil: 'networkidle', timeout: 15000 });
  await page.screenshot({ path: '${outPath.replace(/\\/g, '\\\\')}', fullPage: false });
  await browser.close();
  console.log(JSON.stringify({ path: '${outPath.replace(/\\/g, '\\\\')}' }));
})();
`;
  const tmpScript = join(homedir(), 'tmp-screenshot.cjs');
  await writeFile(tmpScript, script);
  const result = execSync(`node "${tmpScript}"`, { encoding: 'utf-8' });
  const { path: screenshotPath } = JSON.parse(result.trim());
  return screenshotPath;
}

// ── 解析参数 ────────────────────────────────────────────────────
function parseArgs() {
  const args = process.argv.slice(2);
  const result = { url: 'http://localhost:5173', design: null, codeOnly: false };
  for (let i = 0; i < args.length; i++) {
    if (args[i] === '--url') result.url = args[++i];
    if (args[i] === '--design') result.design = args[++i];
    if (args[i] === '--code-only') result.codeOnly = true;
  }
  return result;
}

// ── 主流程 ──────────────────────────────────────────────────────
async function main() {
  const { url, design: designPath, codeOnly } = parseArgs();

  if (!process.env.VAULT_MASTER_KEY) process.env.VAULT_MASTER_KEY = 'zuiho_kai';
  const apiKey = process.env.GEMINI_API_KEY || await getKeyFromVault('gemini').catch(() => null);

  // 读取设计稿（如有）
  let designSpec = '';
  if (designPath && existsSync(designPath)) {
    designSpec = await readFile(designPath, 'utf-8');
    console.log(`📋 已加载设计稿: ${designPath}`);
  }

  let review;

  if (codeOnly) {
    // ── 代码审查模式（不截图，分析源码）──
    console.log('🔍 代码审查模式（无截图）...\n');
    const prompt = buildCodeReviewPrompt(designSpec);
    console.log('🤖 Gemini CLI 正在审查代码...\n');
    review = callGeminiText(apiKey, prompt);
  } else {
    // ── 截图视觉审查模式 ──
    console.log(`📸 正在截图 ${url} ...`);
    const screenshotPath = await takeScreenshot(url);
    console.log(`✅ 截图完成: ${screenshotPath}`);

    const prompt = buildVisionPrompt(designSpec);
    console.log('\n🤖 Gemini CLI 正在审查截图...\n');
    review = callGeminiVision(apiKey, screenshotPath, prompt);
  }

  // 判断是否通过
  const passed = review.includes('**PASS**') || review.includes('PASS');
  const score = review.match(/综合评分[：:]\s*(\d+)\/10/)?.[1] || '?';

  console.log('═'.repeat(60));
  console.log(review);
  console.log('═'.repeat(60));

  // 保存报告
  const reviewDir = join(process.cwd(), 'docs', 'specs', '_ui-reviews');
  await mkdir(reviewDir, { recursive: true });
  const timestamp = new Date().toISOString().slice(0, 10);
  const label = codeOnly ? '代码美学审查' : '视觉美学审查';
  const outPath = join(reviewDir, `${timestamp}-${label}.md`);

  const report = `# UI 美学审查报告 — ${label}

> 审查时间：${new Date().toLocaleString('zh-CN')}
> 审查范围：${codeOnly ? '全部前端源码' : url}
> 审查模型：${codeOnly ? 'gemini-2.5-flash-lite' : 'gemini-2.5-flash'}
> 阶段：开发流程阶段 6.5

---

${review}
`;

  await writeFile(outPath, report, 'utf-8');
  console.log(`\n📄 审查报告已保存: ${outPath}`);
  console.log(`\n${passed ? '✅ PASS' : '❌ FAIL'} — 综合评分 ${score}/10`);

  process.exit(passed ? 0 : 1);
}

function buildVisionPrompt(designSpec) {
  return `你是一位顶级 UI/UX 设计师，正在对一个 Discord 风格的社区应用做美学验收审查。

${designSpec ? `## 原始设计稿（验收标准参考）\n${designSpec}\n\n---\n` : ''}

## 审查维度（逐项打分 1-10）

1. **视觉层级**：信息优先级是否通过字号/字重/颜色体现清晰？
2. **颜色和谐**：色彩搭配是否协调？主题色使用是否一致？
3. **间距一致性**：组件间距、内边距是否统一有规律？
4. **字体排版**：字体大小层级、行高、可读性？
5. **组件对齐**：元素是否对齐整齐？网格感如何？
6. **交互反馈**：按钮/可点击元素是否有明确的视觉提示？
7. **整体美观度**：综合视觉感受

## 输出格式

### 综合评分：X/10

### ✅ 做得好的地方
- （列出 2-3 条具体优点）

### ❌ 问题清单
| 严重程度 | 问题描述 | 建议修复方式 |
|---------|---------|------------|
| P0 严重 | ... | ... |
| P1 重要 | ... | ... |
| P2 建议 | ... | ... |

### 🎯 优先修复项（Top 3）
1.
2.
3.

### 最终结论
**PASS** 或 **FAIL**（7分以上且无 P0 问题为 PASS）

用中文回答，要具体（指出屏幕上的具体位置/颜色/数值），不要泛泛而谈。`;
}

function buildCodeReviewPrompt(designSpec) {
  return `你是一位资深 UI/UX 工程师，精通 CSS 美学审查。请对提供的前端源码做完整的美学与可访问性审查。

${designSpec ? `## 原始设计稿（验收标准参考）\n${designSpec}\n\n---\n` : ''}

## 审查维度
1. 触摸目标尺寸（P0：<44px 的可交互元素）
2. 间距体系（是否遵循 4/8px 倍数网格）
3. 颜色对比度（text vs background，WCAG AA 标准）
4. CSS 变量一致性（硬编码颜色 vs 变量系统）
5. 字体排印（font-size 层级、font-weight 使用）
6. 动画/过渡（有无不一致或缺失）
7. 响应式（有无写死的 px 导致布局风险）

## 输出格式

### 综合评分：X/10

### 🏆 做得好的地方
- （列出 3-5 条具体优点）

### 🔴 P0 严重问题（必须修复）
- **文件名 ~行号** | 问题描述 | 修复建议

### 🟡 P1 重要问题（建议修复）
- 同上格式

### 🔵 P2 优化建议
- 同上格式

### 📋 总结

用中文输出，格式清晰，列出文件名和行号。`;
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });

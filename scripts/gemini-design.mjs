#!/usr/bin/env node
/**
 * gemini-design.mjs
 * 阶段 2.5：UI 设计稿生成
 *
 * 用法：
 *   node scripts/gemini-design.mjs "功能描述"
 *   node scripts/gemini-design.mjs "添加用户设置面板，包含主题切换和通知开关"
 *
 * 输出：docs/specs/SPEC-XXX/ui-design.md（设计稿）
 */

import { readFile, writeFile, mkdir } from 'fs/promises';
import { join, dirname } from 'path';
import { homedir } from 'os';
import { createDecipheriv, scryptSync } from 'crypto';
import { existsSync } from 'fs';
import { execSync, spawnSync } from 'child_process';
import { mkdirSync } from 'fs';

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

// ── 读取现有主题 Token（给 Gemini 作为设计约束）──────────────────
async function readThemeTokens() {
  const themePath = join(process.cwd(), 'web', 'src', 'themes.css');
  if (!existsSync(themePath)) return '';
  const css = await readFile(themePath, 'utf-8');
  // 提取 civitas 主题的 CSS 变量
  const match = css.match(/:root[^{]*\{([^}]+)\}/s);
  return match ? match[1].trim() : '';
}

// ── 调用 Gemini CLI（从 vault 读 key 注入环境变量）───────────────
async function callGemini(apiKey, prompt) {
  // 每次新建 session，用 stdin pipe 方式传 prompt（避免 shell 转义问题）
  const env = { ...process.env };
  if (apiKey) env.GEMINI_API_KEY = apiKey;
  const r = spawnSync('gemini', ['-m', 'gemini-2.5-flash'], {
    input: prompt,
    encoding: 'utf-8',
    timeout: 120_000,
    shell: true,
    env,
  });
  if (r.error) throw r.error;
  if (r.status !== 0) throw new Error(r.stderr || `gemini exit ${r.status}`);
  return r.stdout.split('\n')
    .filter(l => !l.includes('DeprecationWarning') && !l.includes('punycode') && !l.includes('Hook registry') && !l.includes('initialized'))
    .join('\n').trim();
}

// ── 主流程 ──────────────────────────────────────────────────────
async function main() {
  const feature = process.argv[2];
  if (!feature) {
    console.error('用法: node scripts/gemini-design.mjs "功能描述"');
    process.exit(1);
  }

  // 从 vault 读取 API key（优先 env，其次 vault）
  if (!process.env.VAULT_MASTER_KEY) process.env.VAULT_MASTER_KEY = 'zuiho_kai';
  const apiKey = process.env.GEMINI_API_KEY || await getKeyFromVault('gemini').catch(() => null);

  // 读取主题约束
  const themeTokens = await readThemeTokens();

  const prompt = `你是一位专业的 UI/UX 设计师，正在为一个 Discord 风格的社区应用设计界面。

## 技术栈
- React + TypeScript
- 纯 CSS（无 UI 库，手写 CSS 变量）
- 布局：Discord 风格（左侧 Rail 72px → 频道栏 240px → 主内容区 → 右侧信息栏 240px）

## 现有 CSS 设计 Token（必须复用，不能自创颜色）
\`\`\`css
${themeTokens}
\`\`\`

## 需要设计的功能
${feature}

## 要求
请输出一份完整的 UI 设计稿，包含：

### 1. 组件结构
列出需要创建/修改的组件树，例如：
\`\`\`
FeaturePanel/
  ├── FeatureHeader（标题区）
  ├── FeatureBody（主内容）
  │   ├── ItemList（列表）
  │   └── ItemCard（卡片）
  └── FeatureFooter（操作区）
\`\`\`

### 2. 布局规格
- 每个区域的尺寸（px 或 %）
- Flex/Grid 布局方向
- 间距（padding/margin/gap）

### 3. 视觉规格
- 背景色：使用哪个 CSS 变量
- 文字色：使用哪个 CSS 变量
- 边框：1px solid var(--xxx)
- 圆角：xpx
- 阴影（如有）

### 4. 交互状态
- hover 效果
- active/selected 状态
- empty state（无数据时）
- loading 状态

### 5. 关键 CSS 片段
给出最重要的 2-3 个组件的 CSS 样式代码（使用 CSS 变量）

### 6. 验收标准（供 Gemini 美学审查用）
列出 5 条具体、可视化验证的标准，例如：
- [ ] 卡片间距统一为 8px
- [ ] 主色调使用 --accent-primary
- [ ] 文字层级清晰（主标题 16px bold，副标题 13px regular）

请用中文输出，格式清晰，可直接给 Claude Code 作为实现参考。`;

  console.log('🎨 Gemini 正在生成 UI 设计稿...\n');
  const design = await callGemini(apiKey, prompt);

  // 确定输出路径
  const specDir = join(process.cwd(), 'docs', 'specs', '_ui-designs');
  await mkdir(specDir, { recursive: true });

  const timestamp = new Date().toISOString().slice(0, 10);
  const slug = feature.slice(0, 20).replace(/\s+/g, '-');
  const outPath = join(specDir, `${timestamp}-${slug}.md`);

  const output = `# UI 设计稿：${feature}

> 生成时间：${new Date().toLocaleString('zh-CN')}
> 工具：Gemini 2.0 Flash
> 阶段：开发流程阶段 2.5

---

${design}
`;

  await writeFile(outPath, output, 'utf-8');
  console.log(design);
  console.log(`\n✅ 设计稿已保存到: ${outPath}`);
}

main().catch(e => { console.error('❌', e.message); process.exit(1); });

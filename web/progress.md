# 前端开发进展记录

> 本文件记录前端（web/）的详细开发进展。
> 只有大里程碑完成后才同步到项目总进展 `../claude-progress.txt`。

---

## 当前状态

- **当前任务**: #4 + #6 已完成，Mock 模式 + 自动化测试已就绪，等待后端联调
- **最近完成**: Mock 数据层 + Vitest 组件测试（13 个用例全通过）
- **待办优先级**: 后端就绪后联调验证
- **阻塞问题**: 无

---

## 进展日志

### 2026-02-14

#### 完成 #4 聊天界面 + WebSocket 连接
- **内容**: ChatRoom 主页面、MessageList、MessageBubble、ChatInput、AgentSidebar、useWebSocket Hook
- **文件**:
  - `src/types.ts` — 类型定义（Agent, Message, WS 协议）
  - `src/api.ts` — REST API 封装（fetchAgents, fetchMessages, createAgent）+ Mock 自动降级
  - `src/hooks/useWebSocket.ts` — WebSocket 连接管理、断线重连（指数退避）+ Mock 模拟回复
  - `src/pages/ChatRoom.tsx` — 聊天室主页面
  - `src/components/MessageList.tsx` — 消息列表 + 自动滚动
  - `src/components/MessageBubble.tsx` — 消息气泡（human/agent/system 三种样式）
  - `src/components/ChatInput.tsx` — 输入框 + 发送
  - `src/components/AgentSidebar.tsx` — Agent 列表 + 在线状态
- **协议**: 完全对齐 TDD-001 WebSocket 消息协议（chat_message / new_message / system_event）
- **状态**: ✅ 完成

#### 完成 #6 Agent 列表/创建页面
- **内容**: AgentManager 页面（列表 + 创建表单）
- **文件**:
  - `src/pages/AgentManager.tsx` — Agent 列表、卡片展示、创建表单
- **状态**: ✅ 完成

#### 完成 Mock 数据层
- **内容**: 前端可脱离后端独立运行和测试
- **文件**:
  - `src/mock-data.ts` — 3 个预置 Agent（Alice/Bob/小明）+ 7 条预置消息（覆盖 human/agent/system）
  - `src/api.ts` — 自动检测后端可用性，不可用时 fallback 到 mock；也可 URL 加 `?mock` 强制启用
  - `src/hooks/useWebSocket.ts` — Mock 模式下本地回显 + 模拟 Agent 随机回复（800-2000ms 延迟）
- **启用方式**: `http://localhost:5173/?mock` 或后端不可用时自动启用
- **状态**: ✅ 完成

#### 完成自动化组件测试
- **内容**: Vitest + Testing Library，模拟用户点击/输入/按键
- **文件**:
  - `src/test-setup.ts` — 测试环境配置
  - `src/__tests__/components.test.tsx` — 13 个测试用例
- **测试覆盖**:
  - MessageBubble: agent/human/system 三种消息渲染
  - ChatInput: 发送、清空、空消息拦截、Enter 发送、禁用状态
  - MessageList: 空状态、多消息渲染
  - AgentSidebar: Agent 名称、计数、在线/离线状态
- **运行**: `npm test`（13/13 通过）
- **状态**: ✅ 完成

#### 基础设施
- Vite proxy 配置（/api → localhost:8000）
- Vitest 配置（jsdom 环境、globals、setup file）
- App 导航（聊天室 / Agent 管理 切换）
- 暗色主题 UI 样式
- TypeScript 严格模式编译通过

---

## 待办事项

- [ ] @提及自动补全（ChatInput 增强，Phase 2）
- [ ] agent_typing 事件展示（Phase 2）
- [ ] since_id 增量拉取消息（Phase 2）
- [ ] 联调验证（等后端 #1 完成）

---

## 技术债务

- [ ] 聊天界面缺少虚拟滚动（消息过多时性能问题）
- [ ] 未实现消息本地缓存

---

## 大里程碑记录

> 完成大里程碑后，同步到 ../claude-progress.txt

### M1.1 - 聊天界面 + WebSocket 客户端
- **完成时间**: 2026-02-14
- **包含内容**: 聊天 UI + WebSocket 连接 + 实时消息显示 + Agent 管理页面 + Mock 数据层 + 13 个自动化测试
- **验证标准**: TypeScript 编译通过，13/13 测试通过，Mock 模式可独立运行
- **同步状态**: ✅ 已同步到 claude-progress.txt

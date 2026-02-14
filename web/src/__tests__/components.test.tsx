import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, it, expect } from 'vitest'
import { MessageBubble } from '../components/MessageBubble'
import { ChatInput } from '../components/ChatInput'
import { MessageList } from '../components/MessageList'
import { AgentSidebar } from '../components/AgentSidebar'
import type { Message, Agent } from '../types'

// ========== MessageBubble ==========

describe('MessageBubble', () => {
  const agentMsg: Message = {
    id: 1,
    agent_id: 1,
    agent_name: 'Alice',
    sender_type: 'agent',
    message_type: 'chat',
    content: '大家好！',
    mentions: [],
    created_at: '2026-02-14 10:00:00',
  }

  const humanMsg: Message = {
    id: 2,
    agent_id: 0,
    agent_name: 'Human',
    sender_type: 'human',
    message_type: 'chat',
    content: '你好 Alice',
    mentions: [],
    created_at: '2026-02-14 10:01:00',
  }

  const systemMsg: Message = {
    id: 3,
    agent_id: 0,
    agent_name: 'System',
    sender_type: 'system',
    message_type: 'system',
    content: 'Alice 已上线',
    mentions: [],
    created_at: '2026-02-14 10:02:00',
  }

  it('renders agent message with name and content', () => {
    render(<MessageBubble message={agentMsg} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('大家好！')).toBeInTheDocument()
  })

  it('renders human message with correct style', () => {
    const { container } = render(<MessageBubble message={humanMsg} />)
    expect(container.querySelector('.msg-human')).toBeInTheDocument()
    expect(screen.getByText('你好 Alice')).toBeInTheDocument()
  })

  it('renders system message differently', () => {
    const { container } = render(<MessageBubble message={systemMsg} />)
    expect(container.querySelector('.msg-system')).toBeInTheDocument()
    expect(screen.getByText('Alice 已上线')).toBeInTheDocument()
  })
})

// ========== ChatInput ==========

describe('ChatInput', () => {
  it('calls onSend with trimmed text when user types and clicks send', async () => {
    const user = userEvent.setup()
    let sent = ''
    render(<ChatInput onSend={(msg) => { sent = msg }} />)

    const input = screen.getByPlaceholderText(/输入消息/)
    await user.type(input, '  Hello World  ')
    await user.click(screen.getByRole('button', { name: '发送' }))

    expect(sent).toBe('Hello World')
  })

  it('clears input after sending', async () => {
    const user = userEvent.setup()
    render(<ChatInput onSend={() => {}} />)

    const input = screen.getByPlaceholderText(/输入消息/) as HTMLInputElement
    await user.type(input, 'test message')
    await user.click(screen.getByRole('button', { name: '发送' }))

    expect(input.value).toBe('')
  })

  it('does not send empty messages', async () => {
    const user = userEvent.setup()
    let called = false
    render(<ChatInput onSend={() => { called = true }} />)

    await user.click(screen.getByRole('button', { name: '发送' }))
    expect(called).toBe(false)
  })

  it('sends on Enter key', async () => {
    const user = userEvent.setup()
    let sent = ''
    render(<ChatInput onSend={(msg) => { sent = msg }} />)

    const input = screen.getByPlaceholderText(/输入消息/)
    await user.type(input, 'Enter test{Enter}')

    expect(sent).toBe('Enter test')
  })

  it('disables input and button when disabled prop is true', () => {
    render(<ChatInput onSend={() => {}} disabled />)
    expect(screen.getByPlaceholderText(/输入消息/)).toBeDisabled()
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled()
  })
})

// ========== MessageList ==========

describe('MessageList', () => {
  it('shows empty state when no messages', () => {
    render(<MessageList messages={[]} />)
    expect(screen.getByText(/还没有消息/)).toBeInTheDocument()
  })

  it('renders all messages', () => {
    const messages: Message[] = [
      {
        id: 1, agent_id: 1, agent_name: 'Alice', sender_type: 'agent',
        message_type: 'chat', content: '消息一', mentions: [], created_at: '2026-02-14 10:00:00',
      },
      {
        id: 2, agent_id: 2, agent_name: 'Bob', sender_type: 'agent',
        message_type: 'chat', content: '消息二', mentions: [], created_at: '2026-02-14 10:01:00',
      },
    ]
    render(<MessageList messages={messages} />)
    expect(screen.getByText('消息一')).toBeInTheDocument()
    expect(screen.getByText('消息二')).toBeInTheDocument()
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })
})

// ========== AgentSidebar ==========

describe('AgentSidebar', () => {
  const agents: Agent[] = [
    { id: 1, name: 'Alice', persona: '', model: '', avatar: '', status: 'idle', credits: 100, speak_interval: 60, daily_free_quota: 10, quota_used_today: 0 },
    { id: 2, name: 'Bob', persona: '', model: '', avatar: '', status: 'idle', credits: 80, speak_interval: 120, daily_free_quota: 10, quota_used_today: 0 },
  ]

  it('renders agent names', () => {
    render(<AgentSidebar agents={agents} onlineIds={new Set<number>()} />)
    expect(screen.getByText('Alice')).toBeInTheDocument()
    expect(screen.getByText('Bob')).toBeInTheDocument()
  })

  it('shows agent count', () => {
    render(<AgentSidebar agents={agents} onlineIds={new Set<number>()} />)
    expect(screen.getByText('Agents (2)')).toBeInTheDocument()
  })

  it('shows online status correctly', () => {
    const { container } = render(<AgentSidebar agents={agents} onlineIds={new Set([1])} />)
    const dots = container.querySelectorAll('.agent-dot')
    expect(dots[0]).toHaveClass('online')
    expect(dots[1]).toHaveClass('offline')
  })
})

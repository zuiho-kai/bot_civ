import type { Agent, Message } from './types'
import { MOCK_AGENTS, MOCK_MESSAGES } from './mock-data'

const BASE = '/api'

// mock 模式：URL 带 ?mock 或后端不可用时自动启用
let _useMock: boolean | null = null

export async function useMock(): Promise<boolean> {
  if (_useMock !== null) return _useMock
  if (new URLSearchParams(location.search).has('mock')) {
    _useMock = true
    return true
  }
  try {
    const res = await fetch(`${BASE}/health`, { signal: AbortSignal.timeout(2000) })
    _useMock = !res.ok
  } catch {
    _useMock = true
  }
  return _useMock
}

export async function fetchAgents(): Promise<Agent[]> {
  if (await useMock()) return MOCK_AGENTS
  const res = await fetch(`${BASE}/agents/`)
  if (!res.ok) throw new Error(`fetchAgents: ${res.status}`)
  return res.json()
}

export async function fetchAgent(id: number): Promise<Agent> {
  if (await useMock()) {
    const a = MOCK_AGENTS.find((a) => a.id === id)
    if (!a) throw new Error('Agent not found')
    return a
  }
  const res = await fetch(`${BASE}/agents/${id}`)
  if (!res.ok) throw new Error(`fetchAgent: ${res.status}`)
  return res.json()
}

export async function createAgent(data: {
  name: string
  persona: string
  model: string
  avatar?: string
}): Promise<Agent> {
  if (await useMock()) {
    const newAgent: Agent = {
      id: Date.now(),
      name: data.name,
      persona: data.persona,
      model: data.model,
      avatar: data.avatar ?? '',
      status: 'idle',
      credits: 100,
      speak_interval: 60,
      daily_free_quota: 10,
      quota_used_today: 0,
    }
    MOCK_AGENTS.push(newAgent)
    return newAgent
  }
  const res = await fetch(`${BASE}/agents/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`createAgent: ${res.status}`)
  return res.json()
}

export async function fetchMessages(limit = 50): Promise<Message[]> {
  if (await useMock()) return MOCK_MESSAGES.slice(-limit)
  const res = await fetch(`${BASE}/messages?limit=${limit}`)
  if (!res.ok) throw new Error(`fetchMessages: ${res.status}`)
  return res.json()
}

export async function updateAgent(
  id: number,
  data: Partial<Omit<Agent, 'id'>>,
): Promise<Agent> {
  if (await useMock()) {
    const a = MOCK_AGENTS.find((a) => a.id === id)
    if (!a) throw new Error('Agent not found')
    Object.assign(a, data)
    return a
  }
  const res = await fetch(`${BASE}/agents/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`updateAgent: ${res.status}`)
  return res.json()
}

export async function deleteAgent(id: number): Promise<void> {
  if (await useMock()) {
    const idx = MOCK_AGENTS.findIndex((a) => a.id === id)
    if (idx !== -1) MOCK_AGENTS.splice(idx, 1)
    return
  }
  const res = await fetch(`${BASE}/agents/${id}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`deleteAgent: ${res.status}`)
}

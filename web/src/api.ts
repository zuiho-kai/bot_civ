import type { Agent, Message, Bounty, Job, CheckInResult, ShopItem, PurchaseResult, AgentItem, Memory, MemoryListResponse, MemoryStats, CityOverview, Building, ProductionLog, WorkerResult, EatResult } from './types'
import { MOCK_AGENTS, MOCK_MESSAGES, MOCK_BOUNTIES } from './mock-data'

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
      satiety: 100,
      mood: 100,
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

// --- Bounty API ---

export async function fetchBounties(status?: string): Promise<Bounty[]> {
  if (await useMock()) {
    return status ? MOCK_BOUNTIES.filter((b) => b.status === status) : [...MOCK_BOUNTIES]
  }
  const params = status ? `?status=${status}` : ''
  const res = await fetch(`${BASE}/bounties/${params}`)
  if (!res.ok) throw new Error(`fetchBounties: ${res.status}`)
  return res.json()
}

export async function createBounty(data: {
  title: string
  description?: string
  reward: number
}): Promise<Bounty> {
  if (await useMock()) {
    const b: Bounty = {
      id: Date.now(),
      title: data.title,
      description: data.description ?? '',
      reward: data.reward,
      status: 'open',
      claimed_by: null,
      created_at: new Date().toISOString(),
      completed_at: null,
    }
    MOCK_BOUNTIES.push(b)
    return b
  }
  const res = await fetch(`${BASE}/bounties/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`createBounty: ${res.status}`)
  return res.json()
}

export async function claimBounty(bountyId: number, agentId: number): Promise<Bounty> {
  if (await useMock()) {
    const b = MOCK_BOUNTIES.find((b) => b.id === bountyId)
    if (!b || b.status !== 'open') throw new Error('Cannot claim')
    b.status = 'claimed'
    b.claimed_by = agentId
    return b
  }
  const res = await fetch(`${BASE}/bounties/${bountyId}/claim?agent_id=${agentId}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`claimBounty: ${res.status}`)
  return res.json()
}

export async function completeBounty(bountyId: number, agentId: number): Promise<Bounty> {
  if (await useMock()) {
    const b = MOCK_BOUNTIES.find((b) => b.id === bountyId)
    if (!b || b.status !== 'claimed') throw new Error('Cannot complete')
    b.status = 'completed'
    b.completed_at = new Date().toISOString()
    return b
  }
  const res = await fetch(`${BASE}/bounties/${bountyId}/complete?agent_id=${agentId}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`completeBounty: ${res.status}`)
  return res.json()
}

// --- Work API ---

export async function fetchJobs(): Promise<Job[]> {
  if (await useMock()) return []
  const res = await fetch(`${BASE}/work/jobs`)
  if (!res.ok) throw new Error(`fetchJobs: ${res.status}`)
  return res.json()
}

export async function checkIn(jobId: number, agentId: number): Promise<CheckInResult> {
  if (await useMock()) return { ok: false, reason: 'mock_mode', reward: 0, checkin_id: null }
  const res = await fetch(`${BASE}/work/jobs/${jobId}/checkin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  })
  if (!res.ok) throw new Error(`checkIn: ${res.status}`)
  return res.json()
}

// --- Shop API ---

export async function fetchShopItems(): Promise<ShopItem[]> {
  if (await useMock()) return []
  const res = await fetch(`${BASE}/shop/items`)
  if (!res.ok) throw new Error(`fetchShopItems: ${res.status}`)
  return res.json()
}

export async function purchaseItem(agentId: number, itemId: number): Promise<PurchaseResult> {
  if (await useMock()) return { ok: false, reason: 'mock_mode', item_name: null, price: null, remaining_credits: null }
  const res = await fetch(`${BASE}/shop/purchase`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId, item_id: itemId }),
  })
  if (!res.ok) throw new Error(`purchaseItem: ${res.status}`)
  return res.json()
}

export async function fetchAgentItems(agentId: number): Promise<AgentItem[]> {
  if (await useMock()) return []
  const res = await fetch(`${BASE}/shop/agents/${agentId}/items`)
  if (!res.ok) throw new Error(`fetchAgentItems: ${res.status}`)
  return res.json()
}

// --- Memory API ---

export async function fetchMemories(params: {
  agent_id?: number
  type?: string
  page: number
  page_size: number
}): Promise<MemoryListResponse> {
  if (await useMock()) return { items: [], total: 0 }
  const q = new URLSearchParams()
  if (params.agent_id !== undefined) q.set('agent_id', String(params.agent_id))
  if (params.type) q.set('memory_type', params.type)
  q.set('page', String(params.page))
  q.set('page_size', String(params.page_size))
  const res = await fetch(`${BASE}/memories?${q}`)
  if (!res.ok) throw new Error(`fetchMemories: ${res.status}`)
  return res.json()
}

export async function fetchMemoryStats(agentId: number): Promise<MemoryStats> {
  if (await useMock()) return { total: 0, by_type: {} }
  const res = await fetch(`${BASE}/memories/stats?agent_id=${agentId}`)
  if (!res.ok) throw new Error(`fetchMemoryStats: ${res.status}`)
  return res.json()
}

// --- City API ---

export async function fetchCityOverview(city: string): Promise<CityOverview> {
  if (await useMock()) return { resources: [], buildings: [], agents: [] }
  const res = await fetch(`${BASE}/cities/${encodeURIComponent(city)}/overview`)
  if (!res.ok) throw new Error(`fetchCityOverview: ${res.status}`)
  return res.json()
}

export async function fetchBuildingDetail(city: string, buildingId: number): Promise<Building> {
  if (await useMock()) throw new Error('mock_mode')
  const res = await fetch(`${BASE}/cities/${encodeURIComponent(city)}/buildings/${buildingId}`)
  if (!res.ok) throw new Error(`fetchBuildingDetail: ${res.status}`)
  return res.json()
}

export async function assignWorker(city: string, buildingId: number, agentId: number): Promise<WorkerResult> {
  if (await useMock()) return { ok: false, reason: 'mock_mode' }
  const res = await fetch(`${BASE}/cities/${encodeURIComponent(city)}/buildings/${buildingId}/workers`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ agent_id: agentId }),
  })
  if (!res.ok) throw new Error(`assignWorker: ${res.status}`)
  return res.json()
}

export async function removeWorker(city: string, buildingId: number, agentId: number): Promise<WorkerResult> {
  if (await useMock()) return { ok: false, reason: 'mock_mode' }
  const res = await fetch(`${BASE}/cities/${encodeURIComponent(city)}/buildings/${buildingId}/workers/${agentId}`, {
    method: 'DELETE',
  })
  if (!res.ok) throw new Error(`removeWorker: ${res.status}`)
  return res.json()
}

export async function eatFood(agentId: number): Promise<EatResult> {
  if (await useMock()) return { ok: false, reason: 'mock_mode', satiety: 0, mood: 0, stamina: 0 }
  const res = await fetch(`${BASE}/agents/${agentId}/eat`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error(`eatFood: ${res.status}`)
  return res.json()
}

export async function createMemory(data: {
  agent_id: number
  memory_type: string
  content: string
}): Promise<Memory> {
  if (await useMock()) return { id: Date.now(), agent_id: data.agent_id, memory_type: data.memory_type as Memory['memory_type'], content: data.content, access_count: 0, expires_at: null, created_at: new Date().toISOString() }
  const res = await fetch(`${BASE}/memories`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`createMemory: ${res.status}`)
  return res.json()
}

export async function updateMemory(memoryId: number, data: {
  content?: string
  memory_type?: string
}): Promise<Memory> {
  if (await useMock()) throw new Error('mock_mode')
  const res = await fetch(`${BASE}/memories/${memoryId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
  if (!res.ok) throw new Error(`updateMemory: ${res.status}`)
  return res.json()
}

export async function deleteMemory(memoryId: number): Promise<void> {
  if (await useMock()) return
  const res = await fetch(`${BASE}/memories/${memoryId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error(`deleteMemory: ${res.status}`)
}

export async function fetchProductionLogs(city: string, limit = 20): Promise<ProductionLog[]> {
  if (await useMock()) return []
  const res = await fetch(`${BASE}/cities/${encodeURIComponent(city)}/production-logs?limit=${limit}`)
  if (!res.ok) throw new Error(`fetchProductionLogs: ${res.status}`)
  return res.json()
}

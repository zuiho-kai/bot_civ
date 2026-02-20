import type { Agent } from '../types'
import { UserAvatar } from './UserAvatar'

interface AgentStatusPanelProps {
  agents: Agent[]
}

export function AgentStatusPanel({ agents }: AgentStatusPanelProps) {
  const sorted = [...agents].sort((a, b) => {
    const order: Record<string, number> = { executing: 0, thinking: 1, planning: 2, busy: 3, idle: 4, offline: 5 }
    return (order[a.status] ?? 6) - (order[b.status] ?? 6)
  })

  const statusLabel = (agent: Agent): string => {
    switch (agent.status) {
      case 'thinking': return agent.activity || '思考中…'
      case 'executing': return agent.activity || '执行中…'
      case 'planning': return agent.activity || '规划中…'
      case 'idle': return '空闲'
      case 'offline': return '离线'
      default: return agent.activity || ''
    }
  }

  return (
    <div className="info-panel-section agent-status-panel">
      <h3>Agent 状态 — {agents.length}</h3>
      {sorted.map(agent => (
        <div key={agent.id} className="agent-status-item">
          <div className="agent-status-avatar">
            <UserAvatar name={agent.name} size={32} />
            <span className={`agent-status-dot ${agent.status}`} />
          </div>
          <div className="agent-status-info">
            <div className="agent-status-name">{agent.name}</div>
            <div className="agent-status-activity">
              {statusLabel(agent)}
            </div>
          </div>
          <div className="agent-status-credits" title="信用点">
            {agent.credits}c
          </div>
        </div>
      ))}
    </div>
  )
}

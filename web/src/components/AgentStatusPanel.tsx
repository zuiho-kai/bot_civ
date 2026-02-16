import type { Agent } from '../types'
import { UserAvatar } from './UserAvatar'

interface AgentStatusPanelProps {
  agents: Agent[]
}

export function AgentStatusPanel({ agents }: AgentStatusPanelProps) {
  const sorted = [...agents].sort((a, b) => {
    const order = { busy: 0, idle: 1, offline: 2 }
    return (order[a.status] ?? 3) - (order[b.status] ?? 3)
  })

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
              {agent.status === 'busy' && agent.activity
                ? agent.activity
                : agent.status === 'idle'
                  ? '空闲'
                  : agent.status === 'offline'
                    ? '离线'
                    : ''}
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

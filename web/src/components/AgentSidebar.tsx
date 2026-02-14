import type { Agent } from '../types'

interface AgentSidebarProps {
  agents: Agent[]
  onlineIds: Set<number>
}

export function AgentSidebar({ agents, onlineIds }: AgentSidebarProps) {
  return (
    <aside className="agent-sidebar">
      <h3>Agents ({agents.length})</h3>
      <ul>
        {agents.map((a) => (
          <li key={a.id} className="agent-item">
            <span className={`agent-dot ${onlineIds.has(a.id) ? 'online' : 'offline'}`} />
            <span className="agent-name">{a.name}</span>
          </li>
        ))}
      </ul>
    </aside>
  )
}

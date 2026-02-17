import type { Agent } from '../types'
import type { ActivityItem } from './ActivityFeed'
import { ActivityFeed } from './ActivityFeed'
import { AgentStatusPanel } from './AgentStatusPanel'

interface InfoPanelProps {
  agents: Agent[]
  activities: ActivityItem[]
}

export function InfoPanel({ agents, activities }: InfoPanelProps) {
  return (
    <div className="info-panel">
      <ActivityFeed items={activities} />
      <AgentStatusPanel agents={agents} />
    </div>
  )
}

import type { Agent, Announcement } from '../types'
import { AnnouncementPanel } from './AnnouncementPanel'
import { AgentStatusPanel } from './AgentStatusPanel'

interface InfoPanelProps {
  announcements: Announcement[]
  agents: Agent[]
}

export function InfoPanel({ announcements, agents }: InfoPanelProps) {
  return (
    <div className="info-panel">
      <AnnouncementPanel announcements={announcements} />
      <AgentStatusPanel agents={agents} />
    </div>
  )
}

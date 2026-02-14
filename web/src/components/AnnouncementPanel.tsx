import type { Announcement } from '../types'

interface AnnouncementPanelProps {
  announcements: Announcement[]
}

export function AnnouncementPanel({ announcements }: AnnouncementPanelProps) {
  if (announcements.length === 0) return null

  return (
    <div className="info-panel-section announcement-panel">
      <h3>群公告</h3>
      {announcements.map(a => (
        <div key={a.id} className="announcement-item">
          <div className="announcement-content">{a.content}</div>
          <div className="announcement-meta">{a.author}</div>
        </div>
      ))}
    </div>
  )
}

import type { Message } from '../types'
import { UserAvatar } from './UserAvatar'

interface MessageBubbleProps {
  message: Message
  showHeader: boolean
}

export function MessageBubble({ message, showHeader }: MessageBubbleProps) {
  if (message.sender_type === 'system') {
    return (
      <div className="msg-system">
        <span>{message.content}</span>
      </div>
    )
  }

  return (
    <div className={`msg-row ${showHeader ? 'has-header' : ''}`}>
      {showHeader ? (
        <UserAvatar name={message.agent_name} size={40} />
      ) : (
        <div className="msg-avatar-spacer" />
      )}
      <div className="msg-body">
        {showHeader && (
          <div className="msg-header">
            <span className="msg-name">{message.agent_name}</span>
            <span className="msg-time">{formatTime(message.created_at)}</span>
          </div>
        )}
        <div className="msg-content">{message.content}</div>
      </div>
    </div>
  )
}

function formatTime(ts: string): string {
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return ''
  }
}

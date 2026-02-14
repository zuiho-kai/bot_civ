interface ChannelSidebarProps {
  serverName: string
  activeChannel: string
  onChannelSelect: (id: string) => void
}

const CHANNELS = [
  { id: 'general', name: '常规' },
  { id: 'work', name: '工作' },
]

export function ChannelSidebar({ serverName, activeChannel, onChannelSelect }: ChannelSidebarProps) {
  return (
    <div className="channel-sidebar">
      <div className="server-header">{serverName}</div>
      <div className="channel-list">
        <div className="channel-category">文字频道</div>
        {CHANNELS.map(ch => (
          <div
            key={ch.id}
            className={`channel-item ${activeChannel === ch.id ? 'active' : ''}`}
            onClick={() => onChannelSelect(ch.id)}
          >
            <span className="channel-hash">#</span>
            <span>{ch.name}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

type View = 'chat' | 'agents' | 'bounties'

interface ChannelSidebarProps {
  serverName: string
  activeChannel: string
  onChannelSelect: (id: string) => void
  view: View
  onViewChange: (view: View) => void
}

const CHANNELS = [
  { id: 'general', name: '常规' },
  { id: 'work', name: '工作' },
]

export function ChannelSidebar({ serverName, activeChannel, onChannelSelect, view, onViewChange }: ChannelSidebarProps) {
  return (
    <div className="channel-sidebar">
      <div className="server-header">{serverName}</div>
      <div className="channel-list">
        <div className="channel-category">文字频道</div>
        {CHANNELS.map(ch => (
          <div
            key={ch.id}
            className={`channel-item ${view === 'chat' && activeChannel === ch.id ? 'active' : ''}`}
            onClick={() => { onViewChange('chat'); onChannelSelect(ch.id) }}
          >
            <span className="channel-hash">#</span>
            <span>{ch.name}</span>
          </div>
        ))}
        <div className="channel-category">社区</div>
        <div
          className={`channel-item ${view === 'bounties' ? 'active' : ''}`}
          onClick={() => onViewChange('bounties')}
        >
          <span className="channel-hash">!</span>
          <span>悬赏任务</span>
        </div>
      </div>
    </div>
  )
}

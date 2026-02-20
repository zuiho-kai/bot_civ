import { useState, useCallback, useEffect } from 'react'

export interface ActivityItem {
  agent_id: number
  agent_name: string
  action: 'checkin' | 'purchase' | 'chat' | 'rest' | 'assign_building' | 'unassign_building' | 'eat' | 'tool_call'
  reason: string
  timestamp: string
}

const MAX_ITEMS = 50

const ACTION_LABELS: Record<ActivityItem['action'], string> = {
  checkin: '打卡上班',
  purchase: '购买商品',
  chat: '发起聊天',
  rest: '正在休息',
  assign_building: '分配到建筑',
  unassign_building: '离开建筑',
  eat: '进食',
  tool_call: '调用工具',
}

function formatRelativeTime(ts: string): string {
  try {
    const diff = Date.now() - new Date(ts).getTime()
    const mins = Math.floor(diff / 60000)
    if (mins < 1) return '刚刚'
    if (mins < 60) return `${mins} 分钟前`
    const hours = Math.floor(mins / 60)
    if (hours < 24) return `${hours} 小时前`
    return `${Math.floor(hours / 24)} 天前`
  } catch {
    return ''
  }
}

interface ActivityFeedProps {
  items: ActivityItem[]
}

export function ActivityFeed({ items }: ActivityFeedProps) {
  // 每 60s 强制刷新相对时间
  const [, setTick] = useState(0)
  const hasItems = items.length > 0
  useEffect(() => {
    if (!hasItems) return
    const id = setInterval(() => setTick(t => t + 1), 60_000)
    return () => clearInterval(id)
  }, [hasItems])
  return (
    <div className="activity-feed">
      <h3 className="panel-heading">动态</h3>
      {items.length === 0 ? (
        <p className="activity-empty">暂无动态</p>
      ) : (
        <ul className="activity-list" role="log" aria-label="Agent 动态">
          {items.map((item, i) => (
            <li key={`${item.agent_id}-${item.timestamp}-${i}`} className="activity-item">
              <span className="activity-name">{item.agent_name}</span>
              <span className="activity-action">{ACTION_LABELS[item.action]}</span>
              {item.reason && <span className="activity-reason">— {item.reason}</span>}
              <span className="activity-time">{formatRelativeTime(item.timestamp)}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** Hook：管理 ActivityFeed 的状态，供 DiscordLayout 使用 */
export function useActivityFeed() {
  const [items, setItems] = useState<ActivityItem[]>([])

  const pushActivity = useCallback((item: ActivityItem) => {
    setItems(prev => {
      const next = [item, ...prev]
      return next.length > MAX_ITEMS ? next.slice(0, MAX_ITEMS) : next
    })
  }, [])

  return { items, pushActivity }
}

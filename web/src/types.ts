export interface Agent {
  id: number
  name: string
  persona: string
  model: string
  avatar: string
  status: 'idle' | 'busy' | 'offline'
  credits: number
  speak_interval: number
  daily_free_quota: number
  quota_used_today: number
  activity?: string
}

export interface Channel {
  id: string
  name: string
}

export interface Message {
  id: number
  agent_id: number
  agent_name: string
  sender_type: 'human' | 'agent' | 'system'
  message_type: 'chat' | 'work' | 'system'
  content: string
  mentions: number[]
  created_at: string
}

// WebSocket 消息协议
export interface WsSendMessage {
  type: 'chat_message'
  content: string
  message_type?: 'chat' | 'work'
}

export interface WsNewMessage {
  type: 'new_message'
  data: Message
}

export interface WsSystemEvent {
  type: 'system_event'
  data: {
    event: 'agent_online' | 'agent_offline' | 'checkin' | 'purchase' | 'agent_action'
    agent_id: number
    agent_name: string
    timestamp: string
    job_title?: string
    reward?: number
    item_name?: string
    price?: number
    action?: 'checkin' | 'purchase' | 'chat' | 'rest'
    reason?: string
  }
}

export type WsIncoming = WsNewMessage | WsSystemEvent

// 工作岗位
export interface Job {
  id: number
  title: string
  description: string
  daily_reward: number
  max_workers: number
  today_workers: number
}

// 打卡结果
export interface CheckInResult {
  ok: boolean
  reason: string
  reward: number
  checkin_id: number | null
}

// 虚拟商品
export interface ShopItem {
  id: number
  name: string
  description: string
  item_type: 'avatar_frame' | 'title' | 'decoration'
  price: number
}

// 购买结果
export interface PurchaseResult {
  ok: boolean
  reason: string
  item_name: string | null
  price: number | null
  remaining_credits: number | null
}

// Agent 拥有的物品
export interface AgentItem {
  item_id: number
  name: string
  item_type: string
  purchased_at: string
}

// 悬赏任务
export interface Bounty {
  id: number
  title: string
  description: string
  reward: number
  status: 'open' | 'claimed' | 'completed'
  claimed_by: number | null
  created_at: string
  completed_at: string | null
}

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

export interface Announcement {
  id: number
  content: string
  author: string
  created_at: string
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
    event: 'agent_online' | 'agent_offline'
    agent_id: number
    agent_name: string
    timestamp: string
  }
}

export type WsIncoming = WsNewMessage | WsSystemEvent

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

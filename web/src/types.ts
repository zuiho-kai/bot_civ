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
  satiety: number
  mood: number
  stamina: number
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
    event: 'agent_online' | 'agent_offline' | 'checkin' | 'purchase' | 'agent_action' | 'resource_transferred'
    agent_id: number
    agent_name: string
    timestamp: string
    job_title?: string
    reward?: number
    item_name?: string
    price?: number
    action?: string
    reason?: string
    // M5.1: 转赠事件字段
    from_agent_id?: number
    from_agent_name?: string
    to_agent_id?: number
    to_agent_name?: string
    resource_type?: string
    quantity?: number
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

// 记忆系统
export interface Memory {
  id: number
  agent_id: number
  memory_type: 'short' | 'long' | 'public'
  content: string
  access_count: number
  expires_at: string | null
  created_at: string
}

export interface MemoryStats {
  agent_id?: number
  total: number
  by_type: Record<string, number>
}

export interface MemoryListResponse {
  items: Memory[]
  total: number
}

// 城市系统
export interface CityResource {
  resource_type: string
  quantity: number
}

export interface WorkerInfo {
  agent_id: number
  agent_name: string
  assigned_at: string
}

export interface Building {
  id: number
  name: string
  building_type: string
  description: string
  owner: string
  max_workers: number
  workers: WorkerInfo[]
}

export interface CityAgentStatus {
  id: number
  name: string
  satiety: number
  mood: number
  stamina: number
  resources: { resource_type: string; quantity: number }[]
}

export interface CityOverview {
  resources: CityResource[]
  buildings: Building[]
  agents: CityAgentStatus[]
}

export interface ProductionLog {
  id: number
  building_id: number
  input_type: string | null
  input_qty: number
  output_type: string
  output_qty: number
  tick_time: string
}

export interface WorkerResult {
  ok: boolean
  reason: string
}

export interface EatResult {
  ok: boolean
  reason: string
  satiety: number
  mood: number
  stamina: number
}

export interface TransferResult {
  ok: boolean
  reason: string
}

// 交易市场
export interface MarketOrder {
  id: number
  seller_id: number
  seller_name?: string
  sell_type: string
  sell_amount: number
  remain_sell_amount: number
  buy_type: string
  buy_amount: number
  remain_buy_amount: number
  status: 'open' | 'partial' | 'filled' | 'cancelled'
  created_at: string
}

export interface TradeLog {
  id: number
  order_id: number
  seller_id: number
  buyer_id: number
  sell_type: string
  sell_amount: number
  buy_type: string
  buy_amount: number
  created_at: string
}

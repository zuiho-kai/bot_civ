import { useState, useEffect, useCallback } from 'react'
import type { Agent, Message, WsIncoming } from '../types'
import { fetchAgents, fetchMessages } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'
import { useTheme } from '../hooks/useTheme'
import { useActivityFeed } from './ActivityFeed'
import { ServerRail } from './ServerRail'
import { ChannelSidebar } from './ChannelSidebar'
import { InfoPanel } from './InfoPanel'
import { ChatRoom } from '../pages/ChatRoom'
import { AgentManager } from '../pages/AgentManager'
import { BountyBoard } from '../pages/BountyBoard'
import { WorkPanel } from '../pages/WorkPanel'
import { CityPanel } from '../pages/CityPanel'
import { MemoryAdmin } from '../pages/MemoryAdmin'

const HUMAN_AGENT_ID = 0
let _sysMsgSeq = 0

type View = 'chat' | 'agents' | 'bounties' | 'work' | 'city' | 'memory-admin'

export function DiscordLayout() {
  const [messages, setMessages] = useState<Message[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [onlineIds, setOnlineIds] = useState<Set<number>>(new Set())
  const [activeChannel, setActiveChannel] = useState('general')
  const [view, setView] = useState<View>('chat')
  const { items: activities, pushActivity } = useActivityFeed()
  useTheme()

  useEffect(() => {
    fetchMessages().then(setMessages).catch(console.error)
    fetchAgents().then(setAgents).catch(console.error)
  }, [])

  const handleWsMessage = useCallback((msg: WsIncoming) => {
    if (msg.type === 'new_message') {
      setMessages(prev => {
        // 去重：StrictMode 双连接或网络重放可能导致同一消息到达两次
        if (prev.some(m => m.id === msg.data.id)) return prev
        return [...prev, msg.data]
      })
    } else if (msg.type === 'system_event') {
      const { event, agent_id } = msg.data
      setOnlineIds(prev => {
        const next = new Set(prev)
        if (event === 'agent_online') next.add(agent_id)
        else if (event === 'agent_offline') next.delete(agent_id)
        return next
      })
      // 打卡/购买事件 → 刷新 agent 列表（credits 变化）
      if (msg.data.event === 'checkin' || msg.data.event === 'purchase') {
        fetchAgents().then(setAgents).catch(console.error)
      }
      // agent_action 事件 → 推送到 ActivityFeed + 聊天区系统消息
      if (msg.data.event === 'agent_action' && msg.data.action) {
        pushActivity({
          agent_id: msg.data.agent_id,
          agent_name: msg.data.agent_name,
          action: msg.data.action,
          reason: msg.data.reason || '',
          timestamp: msg.data.timestamp,
        })
        // 插入聊天区系统消息
        const actionLabels: Record<string, string> = {
          checkin: '打卡上班',
          purchase: '购买商品',
          chat: '发起聊天',
          rest: '正在休息',
          farm_work: '农田劳作',
          mill_work: '磨坊工作',
          eat: '进食',
        }
        const label = actionLabels[msg.data.action] || msg.data.action
        const sysMsg: Message = {
          id: -(++_sysMsgSeq),
          agent_id: msg.data.agent_id,
          agent_name: msg.data.agent_name,
          sender_type: 'system',
          message_type: 'system',
          content: `${msg.data.agent_name} ${label}`,
          mentions: [],
          created_at: msg.data.timestamp,
        }
        setMessages(prev => [...prev, sysMsg])
        // checkin/purchase 行为也刷新 agent 列表
        if (msg.data.action === 'checkin' || msg.data.action === 'purchase') {
          fetchAgents().then(setAgents).catch(console.error)
        }
      }
      // F35: agent_status_change → 实时更新 agent 状态和 activity
      if (msg.data.event === 'agent_status_change' && msg.data.status) {
        setAgents(prev => prev.map(a =>
          a.id === msg.data.agent_id
            ? { ...a, status: msg.data.status as Agent['status'], activity: msg.data.activity || '' }
            : a
        ))
      }
    }
  }, [pushActivity])

  const { send, connected } = useWebSocket(HUMAN_AGENT_ID, handleWsMessage)

  const handleSend = useCallback(
    (content: string) => {
      send({ type: 'chat_message', content })
    },
    [send],
  )

  const handleSettingsClick = () => {
    setView(view === 'agents' ? 'chat' : 'agents')
  }

  const handleViewChange = (v: View) => {
    setView(v)
  }

  return (
    <div className="discord-layout">
      <ServerRail onSettingsClick={handleSettingsClick} />
      <ChannelSidebar
        serverName="OpenClaw"
        activeChannel={activeChannel}
        onChannelSelect={setActiveChannel}
        view={view}
        onViewChange={handleViewChange}
      />
      <div className="chat-area">
        {view === 'chat' ? (
          <ChatRoom
            messages={messages}
            connected={connected}
            onSend={handleSend}
            activeChannel={activeChannel}
            agents={agents}
          />
        ) : view === 'agents' ? (
          <AgentManager />
        ) : view === 'work' ? (
          <WorkPanel agents={agents} onCreditsChange={() => fetchAgents().then(setAgents)} />
        ) : view === 'city' ? (
          <CityPanel agents={agents} />
        ) : view === 'memory-admin' ? (
          <MemoryAdmin agents={agents} />
        ) : (
          <BountyBoard agents={agents} />
        )}
      </div>
      <InfoPanel agents={agents} activities={activities} />
    </div>
  )
}

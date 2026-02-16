import { useState, useEffect, useCallback } from 'react'
import type { Agent, Message, WsIncoming } from '../types'
import { MOCK_ANNOUNCEMENTS } from '../mock-data'
import { fetchAgents, fetchMessages } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'
import { useTheme } from '../hooks/useTheme'
import { ServerRail } from './ServerRail'
import { ChannelSidebar } from './ChannelSidebar'
import { InfoPanel } from './InfoPanel'
import { ChatRoom } from '../pages/ChatRoom'
import { AgentManager } from '../pages/AgentManager'
import { BountyBoard } from '../pages/BountyBoard'

const HUMAN_AGENT_ID = 0

type View = 'chat' | 'agents' | 'bounties'

export function DiscordLayout() {
  const [messages, setMessages] = useState<Message[]>([])
  const [agents, setAgents] = useState<Agent[]>([])
  const [onlineIds, setOnlineIds] = useState<Set<number>>(new Set())
  const [activeChannel, setActiveChannel] = useState('general')
  const [view, setView] = useState<View>('chat')
  const { toggle } = useTheme()

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
    }
  }, [])

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
      <ServerRail onSettingsClick={handleSettingsClick} themeToggle={toggle} />
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
        ) : (
          <BountyBoard agents={agents} />
        )}
      </div>
      <InfoPanel announcements={MOCK_ANNOUNCEMENTS} agents={agents} />
    </div>
  )
}

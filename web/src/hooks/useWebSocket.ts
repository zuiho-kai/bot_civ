import { useEffect, useRef, useCallback, useState } from 'react'
import type { WsIncoming, WsSendMessage, Message } from '../types'
import { useMock } from '../api'
import { MOCK_AGENTS } from '../mock-data'

const RECONNECT_DELAY = 2000
const MAX_RECONNECT_DELAY = 30000

let mockMsgId = 100

export function useWebSocket(agentId: number, onMessage: (msg: WsIncoming) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectDelay = useRef(RECONNECT_DELAY)
  const reconnectTimer = useRef<number>(0)
  const onMessageRef = useRef(onMessage)
  const [connected, setConnected] = useState<boolean>(false)
  const isMockRef = useRef(false)

  onMessageRef.current = onMessage

  // real WebSocket connect
  const connect = useCallback(() => {
    // 防止 StrictMode 双连接：如果已有活跃连接，先关闭
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      wsRef.current.close()
      wsRef.current = null
    }
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${location.host}/api/ws/${agentId}`
    const ws = new WebSocket(url)

    ws.onopen = () => {
      setConnected(true)
      reconnectDelay.current = RECONNECT_DELAY
    }

    ws.onmessage = (e) => {
      try {
        const msg: WsIncoming = JSON.parse(e.data)
        onMessageRef.current(msg)
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      reconnectTimer.current = window.setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, MAX_RECONNECT_DELAY)
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = () => {
      ws.close()
    }

    wsRef.current = ws
  }, [agentId])

  useEffect(() => {
    let cancelled = false
    useMock().then((mock) => {
      if (cancelled) return
      isMockRef.current = mock
      if (mock) {
        setConnected(true)
      } else {
        connect()
      }
    })
    return () => {
      cancelled = true
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
      wsRef.current = null
    }
  }, [connect])

  const send = useCallback((msg: WsSendMessage) => {
    if (isMockRef.current) {
      // mock: echo human message locally
      const humanMsg: Message = {
        id: ++mockMsgId,
        agent_id: 0,
        agent_name: 'Human',
        sender_type: 'human',
        message_type: msg.message_type ?? 'chat',
        content: msg.content,
        mentions: [],
        created_at: new Date().toISOString(),
      }
      onMessageRef.current({ type: 'new_message', data: humanMsg })

      // mock: simulate a random agent reply after a short delay
      const agents = MOCK_AGENTS.filter((a) => a.id !== 0)
      const responder = agents[Math.floor(Math.random() * agents.length)]
      if (responder) {
        setTimeout(() => {
          const reply: Message = {
            id: ++mockMsgId,
            agent_id: responder.id,
            agent_name: responder.name,
            sender_type: 'agent',
            message_type: 'chat',
            content: mockReply(responder.name, msg.content),
            mentions: [],
            created_at: new Date().toISOString(),
          }
          onMessageRef.current({ type: 'new_message', data: reply })
        }, 800 + Math.random() * 1200)
      }
      return
    }

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(msg))
    }
  }, [])

  return { send, connected }
}

function mockReply(name: string, userMsg: string): string {
  const replies = [
    `收到！我来想想...`,
    `有意思，${userMsg.slice(0, 10)}... 让我分析一下`,
    `好的，我觉得这个方向不错`,
    `嗯，这个问题我之前也遇到过`,
    `让我查一下相关资料`,
    `同意！我们可以继续推进`,
  ]
  return `[${name}] ${replies[Math.floor(Math.random() * replies.length)]}`
}

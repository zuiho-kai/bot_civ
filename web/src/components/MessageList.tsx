import { useEffect, useRef } from 'react'
import type { Message } from '../types'
import { MessageBubble } from './MessageBubble'

export function MessageList({ messages }: { messages: Message[] }) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ behavior: 'smooth' })
  }, [messages.length])

  return (
    <div className="message-list">
      {messages.length === 0 && (
        <div className="msg-empty">还没有消息，说点什么吧</div>
      )}
      {messages.map((m, i) => {
        const prev = i > 0 ? messages[i - 1] : null
        const showHeader =
          !prev ||
          prev.sender_type === 'system' ||
          prev.agent_name !== m.agent_name
        return <MessageBubble key={m.id} message={m} showHeader={showHeader} />
      })}
      <div ref={bottomRef} />
    </div>
  )
}

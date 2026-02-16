import type { Message, Agent } from '../types'
import { MessageList } from '../components/MessageList'
import { ChatInput } from '../components/ChatInput'

interface ChatRoomProps {
  messages: Message[]
  connected: boolean
  onSend: (content: string) => void
  activeChannel: string
  agents?: Agent[]
}

export function ChatRoom({ messages, connected, onSend, activeChannel, agents }: ChatRoomProps) {
  return (
    <>
      <header className="chat-header">
        <div className="chat-header-left">
          <span className="channel-hash-header">#</span>
          <h2>{activeChannel === 'general' ? '常规' : '工作'}</h2>
        </div>
        <span className={`conn-status ${connected ? 'on' : 'off'}`}>
          {connected ? '已连接' : '连接中...'}
        </span>
      </header>
      <MessageList messages={messages} />
      <ChatInput onSend={onSend} disabled={!connected} agents={agents} />
    </>
  )
}

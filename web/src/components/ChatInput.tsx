import { useState, useRef, useEffect, type FormEvent, type KeyboardEvent } from 'react'
import type { Agent } from '../types'

interface ChatInputProps {
  onSend: (content: string) => void
  disabled?: boolean
  agents?: Agent[]
}

export function ChatInput({ onSend, disabled, agents = [] }: ChatInputProps) {
  const [text, setText] = useState('')
  const [mentionQuery, setMentionQuery] = useState<string | null>(null)
  const [mentionIndex, setMentionIndex] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  // 过滤匹配的 agent
  const candidates = mentionQuery !== null
    ? agents.filter(a => a.name.toLowerCase().includes(mentionQuery.toLowerCase())).slice(0, 6)
    : []

  const showMention = mentionQuery !== null && candidates.length > 0

  // 检测 @ 输入
  const handleChange = (value: string) => {
    setText(value)
    const input = inputRef.current
    if (!input) { setMentionQuery(null); return }

    const cursor = input.selectionStart ?? value.length
    const before = value.slice(0, cursor)
    // 匹配光标前最近的 @xxx（@ 前面是空格或行首）
    const match = before.match(/(?:^|\s)@([\w\u4e00-\u9fff]*)$/)
    if (match) {
      setMentionQuery(match[1])
      setMentionIndex(0)
    } else {
      setMentionQuery(null)
    }
  }

  // 插入选中的 agent 名
  const insertMention = (agentName: string) => {
    const input = inputRef.current
    if (!input) return

    const cursor = input.selectionStart ?? text.length
    const before = text.slice(0, cursor)
    const after = text.slice(cursor)
    // 替换 @query 为 @agentName
    const replaced = before.replace(/(?:^|\s)@[\w\u4e00-\u9fff]*$/, (m) => {
      const prefix = m.startsWith(' ') ? ' ' : ''
      return `${prefix}@${agentName} `
    })
    const newText = replaced + after
    setText(newText)
    setMentionQuery(null)

    // 恢复焦点和光标
    requestAnimationFrame(() => {
      input.focus()
      const pos = replaced.length
      input.setSelectionRange(pos, pos)
    })
  }

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showMention) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setMentionIndex(i => (i + 1) % candidates.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setMentionIndex(i => (i - 1 + candidates.length) % candidates.length)
    } else if (e.key === 'Enter' || e.key === 'Tab') {
      e.preventDefault()
      insertMention(candidates[mentionIndex].name)
    } else if (e.key === 'Escape') {
      setMentionQuery(null)
    }
  }

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault()
    if (showMention) return // 防止提及选择时误发送
    const trimmed = text.trim()
    if (!trimmed) return
    onSend(trimmed)
    setText('')
    setMentionQuery(null)
  }

  // 点击外部关闭
  useEffect(() => {
    if (!showMention) return
    const handler = (e: MouseEvent) => {
      const target = e.target as HTMLElement
      if (!target.closest('.mention-popup') && !target.closest('.chat-input')) {
        setMentionQuery(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [showMention])

  return (
    <form className="chat-input" onSubmit={handleSubmit}>
      <div className="chat-input-wrapper">
        {showMention && (
          <div className="mention-popup">
            {candidates.map((a, i) => (
              <div
                key={a.id}
                className={`mention-item ${i === mentionIndex ? 'active' : ''}`}
                onMouseDown={(e) => { e.preventDefault(); insertMention(a.name) }}
                onMouseEnter={() => setMentionIndex(i)}
              >
                <span className={`mention-status ${a.status}`} />
                <span className="mention-name">{a.name}</span>
                <span className="mention-role">{a.status === 'busy' ? '忙碌' : a.status === 'idle' ? '空闲' : '离线'}</span>
              </div>
            ))}
          </div>
        )}
        <input
          ref={inputRef}
          type="text"
          value={text}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (@Agent名 可提及)"
          disabled={disabled}
          autoFocus
        />
      </div>
      <button type="submit" disabled={disabled || !text.trim()}>
        发送
      </button>
    </form>
  )
}

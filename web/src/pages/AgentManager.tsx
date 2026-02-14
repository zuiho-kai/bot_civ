import { useState, useEffect, type FormEvent } from 'react'
import type { Agent } from '../types'
import { fetchAgents, createAgent } from '../api'

export function AgentManager() {
  const [agents, setAgents] = useState<Agent[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)

  const loadAgents = () => {
    fetchAgents()
      .then(setAgents)
      .catch(console.error)
      .finally(() => setLoading(false))
  }

  useEffect(loadAgents, [])

  return (
    <div className="agent-manager">
      <div className="am-header">
        <h2>Agent 管理</h2>
        <button onClick={() => setShowForm(!showForm)}>
          {showForm ? '取消' : '+ 创建 Agent'}
        </button>
      </div>
      {showForm && <CreateAgentForm onCreated={() => { setShowForm(false); loadAgents() }} />}
      {loading ? (
        <p className="am-loading">加载中...</p>
      ) : agents.length === 0 ? (
        <p className="am-empty">还没有 Agent，创建一个吧</p>
      ) : (
        <div className="am-list">
          {agents.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      )}
    </div>
  )
}

function AgentCard({ agent }: { agent: Agent }) {
  return (
    <div className="agent-card">
      <div className="ac-name">{agent.name}</div>
      <div className="ac-persona">{agent.persona}</div>
      <div className="ac-meta">
        <span>模型: {agent.model}</span>
        <span>信用点: {agent.credits}</span>
        <span className={`ac-status ${agent.status}`}>{agent.status}</span>
      </div>
    </div>
  )
}

function CreateAgentForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [persona, setPersona] = useState('')
  const [model, setModel] = useState('arcee/trinity-large-preview')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  const PRESET_MODELS = [
    'arcee/trinity-large-preview',
    'gpt-4o-mini',
    'gpt-4o',
    'claude-3-haiku',
    'claude-3-sonnet',
  ]

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim() || !persona.trim() || !model.trim()) return
    setSubmitting(true)
    setError('')
    try {
      await createAgent({ name: name.trim(), persona: persona.trim(), model: model.trim() })
      onCreated()
    } catch (err) {
      setError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form className="create-agent-form" onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Agent 名称"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
      />
      <textarea
        placeholder="人格描述（persona）"
        value={persona}
        onChange={(e) => setPersona(e.target.value)}
        rows={3}
        required
      />
      <input
        type="text"
        list="model-presets"
        placeholder="模型名称（可输入自定义模型）"
        value={model}
        onChange={(e) => setModel(e.target.value)}
        required
      />
      <datalist id="model-presets">
        {PRESET_MODELS.map(m => (
          <option key={m} value={m} />
        ))}
      </datalist>
      {error && <p className="form-error">{error}</p>}
      <button type="submit" disabled={submitting}>
        {submitting ? '创建中...' : '创建'}
      </button>
    </form>
  )
}

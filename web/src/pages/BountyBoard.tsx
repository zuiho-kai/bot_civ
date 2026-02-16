import { useState, useEffect, useCallback } from 'react'
import type { Bounty, Agent } from '../types'
import { fetchBounties, createBounty, claimBounty, completeBounty } from '../api'

interface BountyBoardProps {
  agents: Agent[]
}

type StatusFilter = 'all' | 'open' | 'claimed' | 'completed'

const FILTERS: StatusFilter[] = ['all', 'open', 'claimed', 'completed']
const FILTER_LABELS: Record<StatusFilter, string> = {
  all: '全部', open: '开放', claimed: '进行中', completed: '已完成',
}
const statusLabel = (s: string) =>
  s === 'open' ? '开放' : s === 'claimed' ? '进行中' : '已完成'

export function BountyBoard({ agents }: BountyBoardProps) {
  const [bounties, setBounties] = useState<Bounty[]>([])
  const [filter, setFilter] = useState<StatusFilter>('all')
  const [showForm, setShowForm] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // form state
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [reward, setReward] = useState(10)

  const load = useCallback(() => {
    setLoading(true)
    fetchBounties(filter === 'all' ? undefined : filter)
      .then(setBounties)
      .catch(() => setError('加载失败'))
      .finally(() => setLoading(false))
  }, [filter])

  useEffect(() => { load() }, [load])

  const agentName = (id: number | null) => {
    if (id === null) return ''
    return agents.find(a => a.id === id)?.name ?? `Agent#${id}`
  }

  const handleCreate = async () => {
    if (!title.trim()) return
    setError('')
    try {
      await createBounty({ title: title.trim(), description: description.trim(), reward })
      setTitle('')
      setDescription('')
      setReward(10)
      setShowForm(false)
      load()
    } catch {
      setError('创建失败')
    }
  }

  const handleClaim = async (bountyId: number, agentId: number) => {
    try {
      await claimBounty(bountyId, agentId)
      load()
    } catch {
      setError('接取失败')
    }
  }

  const handleComplete = async (bounty: Bounty) => {
    if (!bounty.claimed_by) return
    try {
      await completeBounty(bounty.id, bounty.claimed_by)
      load()
    } catch {
      setError('完成失败')
    }
  }

  return (
    <div className="bounty-board">
      <div className="bb-header">
        <h2>悬赏任务</h2>
        <button onClick={() => setShowForm(!showForm)}>
          {showForm ? '取消' : '发布悬赏'}
        </button>
      </div>

      {showForm && (
        <div className="bb-form">
          <input
            placeholder="悬赏标题"
            value={title}
            onChange={e => setTitle(e.target.value)}
          />
          <textarea
            placeholder="描述（可选）"
            value={description}
            onChange={e => setDescription(e.target.value)}
            rows={2}
          />
          <div className="bb-form-row">
            <label>
              奖励:
              <input
                type="number"
                min={1}
                max={10000}
                value={reward}
                onChange={e => setReward(Number(e.target.value))}
                className="bb-reward-input"
              />
              <span className="bb-unit">信用点</span>
            </label>
            <button onClick={handleCreate} disabled={!title.trim()}>发布</button>
          </div>
        </div>
      )}

      <div className="bb-filters">
        {FILTERS.map(f => (
          <button
            key={f}
            className={`bb-filter-btn ${filter === f ? 'active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {FILTER_LABELS[f]}
          </button>
        ))}
      </div>

      {error && <div className="form-error">{error}</div>}

      {loading ? (
        <div className="am-loading">加载中...</div>
      ) : bounties.length === 0 ? (
        <div className="am-empty">暂无悬赏任务</div>
      ) : (
        <div className="bb-list">
          {bounties.map(b => (
            <div key={b.id} className={`bb-card bb-status-${b.status}`}>
              <div className="bb-card-header">
                <span className="bb-title">{b.title}</span>
                <span className={`bb-badge bb-badge-${b.status}`}>{statusLabel(b.status)}</span>
              </div>
              {b.description && <div className="bb-desc">{b.description}</div>}
              <div className="bb-card-footer">
                <span className="bb-reward">{b.reward} 信用点</span>
                {b.claimed_by !== null && (
                  <span className="bb-claimed-by">执行: {agentName(b.claimed_by)}</span>
                )}
                <div className="bb-actions">
                  {b.status === 'open' && agents.length > 0 && (
                    <select
                      defaultValue=""
                      onChange={e => {
                        const aid = Number(e.target.value)
                        if (aid) handleClaim(b.id, aid)
                        e.target.value = ''
                      }}
                    >
                      <option value="" disabled>指派 Agent...</option>
                      {agents.map(a => (
                        <option key={a.id} value={a.id}>{a.name}</option>
                      ))}
                    </select>
                  )}
                  {b.status === 'claimed' && (
                    <button className="bb-complete-btn" onClick={() => handleComplete(b)}>
                      标记完成
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

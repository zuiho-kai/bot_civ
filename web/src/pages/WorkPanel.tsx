import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import type { Agent, Job, ShopItem, AgentItem } from '../types'
import { fetchJobs, checkIn, fetchShopItems, purchaseItem, fetchAgentItems } from '../api'

interface WorkPanelProps {
  agents: Agent[]
  onCreditsChange?: () => void
}

type Tab = 'jobs' | 'shop' | 'inventory'
const TAB_LABELS: Record<Tab, string> = { jobs: '岗位', shop: '商店', inventory: '背包' }
const TYPE_LABELS: Record<string, string> = {
  avatar_frame: '头像框',
  title: '称号',
  decoration: '装饰品',
}

export function WorkPanel({ agents, onCreditsChange }: WorkPanelProps) {
  const [tab, setTab] = useState<Tab>('jobs')
  const [jobs, setJobs] = useState<Job[]>([])
  const [items, setItems] = useState<ShopItem[]>([])
  const [ownedItems, setOwnedItems] = useState<AgentItem[]>([])
  const [selectedAgent, setSelectedAgent] = useState<number>(0)
  const [loading, setLoading] = useState(true)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  const nonHumanAgents = useMemo(() => agents.filter(a => a.id !== 0), [agents])
  const currentAgent = agents.find(a => a.id === selectedAgent)

  const filteredAgents = useMemo(() => {
    if (!search.trim()) return nonHumanAgents
    const q = search.toLowerCase()
    return nonHumanAgents.filter(a => a.name.toLowerCase().includes(q))
  }, [nonHumanAgents, search])

  // 点击外部关闭 dropdown
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
        setSearch('')
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  // dropdown 打开时聚焦搜索框
  useEffect(() => {
    if (dropdownOpen) searchRef.current?.focus()
  }, [dropdownOpen])

  const loadData = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      if (tab === 'jobs') {
        setJobs(await fetchJobs())
      } else if (tab === 'shop') {
        setItems(await fetchShopItems())
      } else if (tab === 'inventory' && selectedAgent > 0) {
        setOwnedItems(await fetchAgentItems(selectedAgent))
      }
    } catch {
      setError('加载失败')
    } finally {
      setLoading(false)
    }
  }, [tab, selectedAgent])

  useEffect(() => { loadData() }, [loadData])

  // 默认选中第一个非人类 agent
  useEffect(() => {
    if (selectedAgent === 0 && nonHumanAgents.length > 0) {
      setSelectedAgent(nonHumanAgents[0].id)
    }
  }, [nonHumanAgents.length]) // eslint-disable-line react-hooks/exhaustive-deps

  // 自动清除提示消息
  useEffect(() => {
    if (!message) return
    const t = setTimeout(() => setMessage(''), 3000)
    return () => clearTimeout(t)
  }, [message])

  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(''), 3000)
    return () => clearTimeout(t)
  }, [error])

  const handleCheckIn = async (jobId: number) => {
    if (selectedAgent <= 0) return
    setMessage('')
    setError('')
    try {
      const result = await checkIn(jobId, selectedAgent)
      if (result.ok) {
        setMessage(`打卡成功！获得 ${result.reward} 信用点`)
        onCreditsChange?.()
        loadData()
      } else {
        const reasons: Record<string, string> = {
          already_checked_in: '今日已打卡',
          job_full: '岗位已满',
          agent_not_found: 'Agent 不存在',
        }
        setError(reasons[result.reason] ?? result.reason)
      }
    } catch {
      setError('打卡失败')
    }
  }

  const handlePurchase = async (itemId: number) => {
    if (selectedAgent <= 0) return
    setMessage('')
    setError('')
    try {
      const result = await purchaseItem(selectedAgent, itemId)
      if (result.ok) {
        setMessage(`购买成功！花费 ${result.price} 信用点，剩余 ${result.remaining_credits}`)
        onCreditsChange?.()
        // 购买成功后切到背包
        setTab('inventory')
      } else {
        const reasons: Record<string, string> = {
          insufficient_credits: '余额不足',
          already_owned: '已拥有该物品',
          agent_not_found: 'Agent 不存在',
          item_not_found: '商品不存在',
        }
        setError(reasons[result.reason] ?? result.reason)
      }
    } catch {
      setError('购买失败')
    }
  }

  const selectAgent = (id: number) => {
    setSelectedAgent(id)
    setDropdownOpen(false)
    setSearch('')
  }

  return (
    <div className="work-panel">
      <div className="wp-header">
        <h2>城市经济</h2>
        <div className="wp-agent-dropdown" ref={dropdownRef}>
          <div
            className={`wp-agent-trigger ${dropdownOpen ? 'open' : ''}`}
            onClick={() => setDropdownOpen(v => !v)}
          >
            {currentAgent ? (
              <>
                <div className="wp-agent-avatar">{currentAgent.name[0]}</div>
                <div className="wp-agent-info">
                  <div className="wp-agent-name">{currentAgent.name}</div>
                  <div className="wp-agent-credits">{currentAgent.credits} 信用点</div>
                </div>
              </>
            ) : (
              <span style={{ color: 'var(--text-muted)' }}>选择 Agent...</span>
            )}
            <span className="wp-agent-chevron">▼</span>
          </div>
          {dropdownOpen && (
            <div className="wp-agent-menu">
              <div className="wp-search-box">
                <input
                  ref={searchRef}
                  className="wp-search-input"
                  type="text"
                  placeholder="搜索 Agent..."
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  onClick={e => e.stopPropagation()}
                />
              </div>
              {filteredAgents.map(a => (
                <div
                  key={a.id}
                  className={`wp-agent-option ${a.id === selectedAgent ? 'selected' : ''}`}
                  onClick={() => selectAgent(a.id)}
                >
                  <div className="wp-agent-avatar">{a.name[0]}</div>
                  <div className="wp-agent-info">
                    <div className="wp-agent-name">{a.name}</div>
                    <div className="wp-agent-credits">{a.credits} 信用点</div>
                  </div>
                </div>
              ))}
              {filteredAgents.length === 0 && (
                <div style={{ padding: '8px 10px', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                  {nonHumanAgents.length === 0 ? '暂无 Agent' : '无匹配结果'}
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="wp-tabs">
        {(Object.keys(TAB_LABELS) as Tab[]).map(t => (
          <button
            key={t}
            className={`wp-tab ${tab === t ? 'active' : ''}`}
            onClick={() => setTab(t)}
          >
            {TAB_LABELS[t]}
          </button>
        ))}
      </div>

      {message && <div className="wp-success" role="status" aria-live="polite">{message}</div>}
      {error && <div className="form-error" role="alert" aria-live="assertive">{error}</div>}

      {loading ? (
        <div className="am-loading">加载中...</div>
      ) : selectedAgent <= 0 ? (
        <div className="am-empty">请先选择一个 Agent</div>
      ) : tab === 'jobs' ? (
        <div className="wp-list">
          {jobs.map(job => (
            <div key={job.id} className="wp-card">
              <div className="wp-card-header">
                <span className="wp-title">{job.title}</span>
                <span className="wp-reward">+{job.daily_reward} 信用点</span>
              </div>
              <div className="wp-desc">{job.description}</div>
              <div className="wp-card-footer">
                <span className="wp-capacity">
                  {job.today_workers}/{job.max_workers === 0 ? '∞' : job.max_workers} 在岗
                </span>
                <button
                  className="wp-action-btn"
                  onClick={() => handleCheckIn(job.id)}
                  disabled={job.max_workers > 0 && job.today_workers >= job.max_workers}
                >
                  打卡
                </button>
              </div>
            </div>
          ))}
          {jobs.length === 0 && <div className="am-empty">暂无岗位</div>}
        </div>
      ) : tab === 'shop' ? (
        <div className="wp-list">
          {items.map(item => (
            <div key={item.id} className="wp-card">
              <div className="wp-card-header">
                <span className="wp-title">{item.name}</span>
                <span className="wp-price">{item.price} 信用点</span>
              </div>
              <div className="wp-desc">{item.description}</div>
              <div className="wp-card-footer">
                <span className="wp-type">{TYPE_LABELS[item.item_type] ?? item.item_type}</span>
                <button
                  className="wp-action-btn"
                  onClick={() => handlePurchase(item.id)}
                  disabled={!currentAgent || currentAgent.credits < item.price}
                >
                  购买
                </button>
              </div>
            </div>
          ))}
          {items.length === 0 && <div className="am-empty">暂无商品</div>}
        </div>
      ) : (
        <div className="wp-list">
          {ownedItems.map(item => (
            <div key={item.item_id} className="wp-card wp-owned">
              <div className="wp-card-header">
                <span className="wp-title">{item.name}</span>
                <span className="wp-type">{TYPE_LABELS[item.item_type] ?? item.item_type}</span>
              </div>
              <div className="wp-desc">购买于 {item.purchased_at}</div>
            </div>
          ))}
          {ownedItems.length === 0 && <div className="am-empty">背包空空如也</div>}
        </div>
      )}
    </div>
  )
}

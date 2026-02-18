import { useState, useEffect, useCallback } from 'react'
import type { Agent, Memory, MemoryStats } from '../types'
import { fetchMemories, fetchMemoryStats, createMemory, updateMemory, deleteMemory } from '../api'
import './MemoryAdmin.css'

const PAGE_SIZE = 20
const TYPES = [
  { key: '', label: '全部' },
  { key: 'short', label: '短期' },
  { key: 'long', label: '长期' },
  { key: 'public', label: '公共' },
]

interface MemoryAdminProps {
  agents: Agent[]
}

export function MemoryAdmin({ agents }: MemoryAdminProps) {
  const [memories, setMemories] = useState<Memory[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // 筛选
  const [selectedAgentId, setSelectedAgentId] = useState<number | undefined>(undefined)
  const [selectedType, setSelectedType] = useState('')

  // 统计
  const [stats, setStats] = useState<MemoryStats | null>(null)

  // CRUD 状态
  const [showCreate, setShowCreate] = useState(false)
  const [createAgentId, setCreateAgentId] = useState<number>(0)
  const [createType, setCreateType] = useState('short')
  const [createContent, setCreateContent] = useState('')
  const [editingId, setEditingId] = useState<number | null>(null)
  const [editContent, setEditContent] = useState('')
  const [actionMsg, setActionMsg] = useState('')

  const loadMemories = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchMemories({
        agent_id: selectedAgentId,
        type: selectedType || undefined,
        page,
        page_size: PAGE_SIZE,
      })
      setMemories(data.items)
      setTotal(data.total)
    } catch {
      setError('加载记忆失败')
    } finally {
      setLoading(false)
    }
  }, [selectedAgentId, selectedType, page])

  const loadStats = useCallback(async () => {
    if (selectedAgentId === undefined) {
      setStats(null)
      return
    }
    try {
      const s = await fetchMemoryStats(selectedAgentId)
      setStats(s)
    } catch {
      setStats(null)
    }
  }, [selectedAgentId])

  useEffect(() => { loadMemories() }, [loadMemories])
  useEffect(() => { loadStats() }, [loadStats])

  const handleCreate = async () => {
    if (!createContent.trim() || createAgentId <= 0) return
    try {
      await createMemory({ agent_id: createAgentId, memory_type: createType, content: createContent })
      setShowCreate(false)
      setCreateContent('')
      setActionMsg('创建成功')
      loadMemories()
      loadStats()
    } catch { setError('创建失败') }
  }

  const handleUpdate = async (memoryId: number) => {
    if (!editContent.trim()) return
    try {
      await updateMemory(memoryId, { content: editContent })
      setEditingId(null)
      setEditContent('')
      setActionMsg('更新成功')
      loadMemories()
    } catch { setError('更新失败') }
  }

  const handleDelete = async (memoryId: number) => {
    try {
      await deleteMemory(memoryId)
      setActionMsg('删除成功')
      loadMemories()
      loadStats()
    } catch { setError('删除失败') }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const formatDate = (s: string) => {
    const d = new Date(s)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="memory-admin">
      <div className="ma-header">
        <h2>记忆面板</h2>
        <button className="ma-create-btn" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? '取消' : '+ 新建记忆'}
        </button>
      </div>

      {/* 新建表单 */}
      {showCreate && (
        <div className="ma-create-form">
          <select value={createAgentId} onChange={e => setCreateAgentId(Number(e.target.value))}>
            <option value={0}>选择 Agent...</option>
            {agents.map(a => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          <select value={createType} onChange={e => setCreateType(e.target.value)}>
            <option value="short">短期</option>
            <option value="long">长期</option>
            <option value="public">公共</option>
          </select>
          <textarea
            placeholder="记忆内容..."
            value={createContent}
            onChange={e => setCreateContent(e.target.value)}
            rows={3}
          />
          <button onClick={handleCreate} disabled={!createContent.trim() || createAgentId <= 0}>
            创建
          </button>
        </div>
      )}

      {/* 筛选 */}
      <div className="ma-filters">
        <select
          value={selectedAgentId ?? ''}
          onChange={e => {
            const v = e.target.value
            setSelectedAgentId(v ? Number(v) : undefined)
            setPage(1)
          }}
        >
          <option value="">全部 Agent</option>
          {agents.map(a => (
            <option key={a.id} value={a.id}>{a.name}</option>
          ))}
        </select>

        <div className="ma-type-tabs">
          {TYPES.map(t => (
            <button
              key={t.key}
              className={`ma-tab ${selectedType === t.key ? 'active' : ''}`}
              onClick={() => { setSelectedType(t.key); setPage(1) }}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* 统计 */}
      {stats && (
        <div className="ma-stats">
          <div className="ma-stat-item">
            <span className="ma-stat-value">{stats.by_type['short'] ?? 0}</span>
            <span className="ma-stat-label">短期</span>
          </div>
          <div className="ma-stat-item">
            <span className="ma-stat-value">{stats.by_type['long'] ?? 0}</span>
            <span className="ma-stat-label">长期</span>
          </div>
          <div className="ma-stat-item">
            <span className="ma-stat-value">{stats.by_type['public'] ?? 0}</span>
            <span className="ma-stat-label">公共</span>
          </div>
          <div className="ma-stat-item">
            <span className="ma-stat-value">{stats.total}</span>
            <span className="ma-stat-label">总计</span>
          </div>
        </div>
      )}

      {/* 操作提示 */}
      {actionMsg && <div className="cp-message success" onClick={() => setActionMsg('')}>{actionMsg}</div>}

      {/* 错误 */}
      {error && <div className="form-error">{error}</div>}

      {/* 列表 */}
      {loading ? (
        <div className="am-loading">加载中...</div>
      ) : memories.length === 0 ? (
        <div className="am-empty">暂无记忆数据</div>
      ) : (
        <div className="ma-list">
          {memories.map(m => (
            <div key={m.id} className="ma-memory-card">
              <div className="ma-memory-header">
                <span className={`ma-type-badge ${m.memory_type}`}>{m.memory_type}</span>
                <span className="ma-memory-id">#{m.id}</span>
                <span className="ma-memory-time">{formatDate(m.created_at)}</span>
                <span className="ma-memory-access">访问 {m.access_count} 次</span>
                <button className="ma-edit-btn" onClick={() => { setEditingId(m.id); setEditContent(m.content) }}>编辑</button>
                <button className="ma-delete-btn" onClick={() => handleDelete(m.id)}>删除</button>
              </div>
              {editingId === m.id ? (
                <div className="ma-edit-form">
                  <textarea value={editContent} onChange={e => setEditContent(e.target.value)} rows={3} />
                  <div className="ma-edit-actions">
                    <button onClick={() => handleUpdate(m.id)}>保存</button>
                    <button onClick={() => setEditingId(null)}>取消</button>
                  </div>
                </div>
              ) : (
                <div className="ma-memory-content">{m.content}</div>
              )}
              {m.expires_at && (
                <div className="ma-memory-expires">过期: {formatDate(m.expires_at)}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* 分页 */}
      {total > PAGE_SIZE && (
        <div className="ma-pagination">
          <button disabled={page <= 1} onClick={() => setPage(p => p - 1)}>上一页</button>
          <span>{page} / {totalPages}</span>
          <button disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>下一页</button>
        </div>
      )}
    </div>
  )
}

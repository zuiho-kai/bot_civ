import { useState, useEffect, useCallback } from 'react'
import type { Agent, Building, CityOverview, ProductionLog, EatResult } from '../types'
import {
  fetchCityOverview,
  fetchBuildingDetail,
  assignWorker,
  removeWorker,
  eatFood,
  fetchProductionLogs,
} from '../api'
import './CityPanel.css'

const CITY = '长安'
const RESOURCE_ICONS: Record<string, string> = { wheat: '🌾', flour: '🫓' }
const RESOURCE_NAMES: Record<string, string> = { wheat: '小麦', flour: '面粉' }
const BUILDING_ICONS: Record<string, string> = { farm: '🌾', mill: '⚙️', gov_farm: '🏛️' }

function barColor(value: number): string {
  if (value > 60) return 'green'
  if (value >= 30) return 'yellow'
  return 'red'
}

interface CityPanelProps {
  agents: Agent[]
}

type CitySubView = 'overview' | 'building' | 'agent-status'

export function CityPanel({ agents }: CityPanelProps) {
  const [subView, setSubView] = useState<CitySubView>('overview')
  const [overview, setOverview] = useState<CityOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  // 建筑子视图状态
  const [selectedBuilding, setSelectedBuilding] = useState<Building | null>(null)
  const [logs, setLogs] = useState<ProductionLog[]>([])
  const [assignAgentId, setAssignAgentId] = useState<number>(0)
  const [buildingMsg, setBuildingMsg] = useState('')
  const [buildingErr, setBuildingErr] = useState('')

  // agent 子视图状态
  const [selectedAgentId, setSelectedAgentId] = useState<number>(0)
  const [eatMsg, setEatMsg] = useState('')
  const [eatErr, setEatErr] = useState('')
  const [eating, setEating] = useState(false)

  const loadOverview = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchCityOverview(CITY)
      setOverview(data)
    } catch {
      setError('加载城市数据失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadOverview() }, [loadOverview])

  // 进入建筑详情
  const openBuilding = async (buildingId: number) => {
    try {
      const b = await fetchBuildingDetail(CITY, buildingId)
      setSelectedBuilding(b)
      const l = await fetchProductionLogs(CITY, 10)
      setLogs(l.filter(log => log.building_id === buildingId))
      setAssignAgentId(0)
      setBuildingMsg('')
      setBuildingErr('')
      setSubView('building')
    } catch {
      setError('加载建筑详情失败')
    }
  }

  // 进入 Agent 状态
  const openAgentStatus = (agentId: number) => {
    setSelectedAgentId(agentId)
    setEatMsg('')
    setEatErr('')
    setSubView('agent-status')
  }

  // 分配工人
  const handleAssign = async () => {
    if (!selectedBuilding || assignAgentId <= 0) return
    setBuildingMsg('')
    setBuildingErr('')
    try {
      const result = await assignWorker(CITY, selectedBuilding.id, assignAgentId)
      if (result.ok) {
        setBuildingMsg('分配成功')
        await openBuilding(selectedBuilding.id)
        loadOverview()
      } else {
        setBuildingErr(result.reason)
      }
    } catch {
      setBuildingErr('分配失败')
    }
  }

  // 移除工人
  const handleRemove = async (agentId: number) => {
    if (!selectedBuilding) return
    setBuildingMsg('')
    setBuildingErr('')
    try {
      const result = await removeWorker(CITY, selectedBuilding.id, agentId)
      if (result.ok) {
        setBuildingMsg('移除成功')
        await openBuilding(selectedBuilding.id)
        loadOverview()
      } else {
        setBuildingErr(result.reason)
      }
    } catch {
      setBuildingErr('移除失败')
    }
  }

  // 进食
  const handleEat = async () => {
    if (selectedAgentId <= 0) return
    setEating(true)
    setEatMsg('')
    setEatErr('')
    try {
      const result: EatResult = await eatFood(selectedAgentId)
      if (result.ok) {
        setEatMsg(`进食成功 - 饱腹度: ${result.satiety}, 心情: ${result.mood}, 体力: ${result.stamina}`)
        loadOverview()
      } else {
        setEatErr(result.reason)
      }
    } catch {
      setEatErr('进食失败')
    } finally {
      setEating(false)
    }
  }

  const goBack = () => {
    setSubView('overview')
    setSelectedBuilding(null)
    setSelectedAgentId(0)
  }

  const formatDate = (s: string) => {
    const d = new Date(s)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  if (loading) return <div className="city-panel"><div className="am-loading">加载中...</div></div>
  if (error && !overview) return <div className="city-panel"><div className="form-error">{error}</div></div>

  // === 城市总览 ===
  if (subView === 'overview' && overview) {
    return (
      <div className="city-panel">
        <div className="cp-header">
          <h2>{CITY}</h2>
        </div>

        {/* 资源条 */}
        <div className="cp-resources">
          {overview.resources.map(r => (
            <div key={r.resource_type} className="cp-resource-item">
              <span className="cp-resource-icon">{RESOURCE_ICONS[r.resource_type] ?? '📦'}</span>
              <div className="cp-resource-info">
                <span className="cp-resource-name">{RESOURCE_NAMES[r.resource_type] ?? r.resource_type}</span>
                <span className="cp-resource-qty">{r.quantity}</span>
              </div>
            </div>
          ))}
          {overview.resources.length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>暂无资源数据</div>
          )}
        </div>

        {/* 建筑卡片网格 */}
        <div className="cp-section-title">建筑</div>
        <div className="cp-building-grid">
          {overview.buildings.map(b => (
            <div
              key={b.id}
              className="cp-building-card"
              onClick={() => openBuilding(b.id)}
            >
              <div className="cp-building-icon">{BUILDING_ICONS[b.building_type] ?? '🏠'}</div>
              <div className="cp-building-name">{b.name}</div>
              <div className="cp-building-workers">
                工人: {b.workers.length}/{b.max_workers}
              </div>
            </div>
          ))}
          {overview.buildings.length === 0 && (
            <div className="am-empty">暂无建筑</div>
          )}
        </div>

        {/* 居民状态 */}
        <div className="cp-section-title">居民状态</div>
        <div className="cp-agent-list">
          {overview.agents.map(a => (
            <div
              key={a.id}
              className="cp-agent-row"
              onClick={() => openAgentStatus(a.id)}
            >
              <span className="cp-agent-name">{a.name}</span>
              <div className="cp-agent-bars">
                <div className="cp-bar-row">
                  <span className="cp-bar-label">饱腹</span>
                  <div className="cp-bar-track">
                    <div
                      className={`cp-bar-fill ${barColor(a.satiety)}`}
                      style={{ width: `${a.satiety}%` }}
                    />
                  </div>
                  <span className="cp-bar-value">{a.satiety}</span>
                </div>
                <div className="cp-bar-row">
                  <span className="cp-bar-label">心情</span>
                  <div className="cp-bar-track">
                    <div
                      className={`cp-bar-fill ${barColor(a.mood)}`}
                      style={{ width: `${a.mood}%` }}
                    />
                  </div>
                  <span className="cp-bar-value">{a.mood}</span>
                </div>
                <div className="cp-bar-row">
                  <span className="cp-bar-label">体力</span>
                  <div className="cp-bar-track">
                    <div
                      className={`cp-bar-fill ${barColor(a.stamina)}`}
                      style={{ width: `${a.stamina}%` }}
                    />
                  </div>
                  <span className="cp-bar-value">{a.stamina}</span>
                </div>
              </div>
            </div>
          ))}
          {overview.agents.length === 0 && (
            <div className="am-empty">暂无居民</div>
          )}
        </div>
      </div>
    )
  }

  // === 建筑详情 ===
  if (subView === 'building' && selectedBuilding) {
    const emptySlots = Math.max(0, selectedBuilding.max_workers - selectedBuilding.workers.length)
    // 可分配的 agent：不在当前建筑工人列表中的，从 props.agents 取
    const workerIds = new Set(selectedBuilding.workers.map(w => w.agent_id))
    const availableAgents = agents.filter(a => !workerIds.has(a.id))

    const prodDesc = selectedBuilding.building_type === 'farm'
      ? '每天产出 10 小麦/人（需体力>=20，消耗15体力）'
      : selectedBuilding.building_type === 'mill'
      ? '每天消耗 5 小麦，产出 3 面粉/人（需体力>=20，消耗15体力）'
      : selectedBuilding.building_type === 'gov_farm'
      ? '每天直接产出 5 面粉/人（需体力>=20，消耗15体力）'
      : '无生产功能'

    return (
      <div className="city-panel">
        <div className="cp-header">
          <button className="cp-back-btn" onClick={goBack}>返回</button>
          <h2>{selectedBuilding.name}</h2>
        </div>

        <div className="cp-building-info">
          <h3>{BUILDING_ICONS[selectedBuilding.building_type] ?? ''} {selectedBuilding.name}</h3>
          <div className="cp-building-desc">{selectedBuilding.description}</div>
          <div className="cp-building-meta">
            <span>类型: {BUILDING_ICONS[selectedBuilding.building_type] ?? selectedBuilding.building_type}</span>
            <span>所属: {selectedBuilding.owner}</span>
            <span>容量: {selectedBuilding.max_workers}</span>
          </div>
        </div>

        {/* 工人列表 */}
        <div className="cp-workers-section">
          <div className="cp-section-title">工人</div>
          <div className="cp-worker-list">
            {selectedBuilding.workers.map(w => (
              <div key={w.agent_id} className="cp-worker-item">
                <span className="cp-worker-name">{w.agent_name}</span>
                <span className="cp-worker-time">分配于 {formatDate(w.assigned_at)}</span>
                <button className="cp-remove-btn" onClick={() => handleRemove(w.agent_id)}>
                  移除
                </button>
              </div>
            ))}
            {Array.from({ length: emptySlots }).map((_, i) => (
              <div key={`empty-${i}`} className="cp-empty-slot">空位</div>
            ))}
          </div>

          {emptySlots > 0 && availableAgents.length > 0 && (
            <div className="cp-assign-row">
              <select
                value={assignAgentId}
                onChange={e => setAssignAgentId(Number(e.target.value))}
              >
                <option value={0}>选择 Agent...</option>
                {availableAgents.map(a => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </select>
              <button
                className="cp-assign-btn"
                disabled={assignAgentId <= 0}
                onClick={handleAssign}
              >
                分配
              </button>
            </div>
          )}

          {buildingMsg && <div className="cp-message success">{buildingMsg}</div>}
          {buildingErr && <div className="cp-message error">{buildingErr}</div>}
        </div>

        {/* 生产说明 */}
        <div className="cp-section-title">生产信息</div>
        <div className="cp-production-info">{prodDesc}</div>

        {/* 生产日志 */}
        <div className="cp-section-title">最近生产日志</div>
        {logs.length === 0 ? (
          <div className="am-empty">暂无生产记录</div>
        ) : (
          <div className="cp-log-list">
            {logs.map(l => (
              <div key={l.id} className="cp-log-item">
                <span className="cp-log-time">{formatDate(l.tick_time)}</span>
                {l.input_type && (
                  <span>消耗 {RESOURCE_ICONS[l.input_type] ?? l.input_type} x{l.input_qty}</span>
                )}
                <span className="cp-log-output">
                  产出 {RESOURCE_ICONS[l.output_type] ?? l.output_type} x{l.output_qty}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // === Agent 状态详情 ===
  if (subView === 'agent-status' && overview) {
    const agent = overview.agents.find(a => a.id === selectedAgentId)
    if (!agent) {
      return (
        <div className="city-panel">
          <button className="cp-back-btn" onClick={goBack}>返回</button>
          <div className="am-empty">Agent 不存在</div>
        </div>
      )
    }

    // 查找当前工作建筑
    const workBuilding = overview.buildings.find(b =>
      b.workers.some(w => w.agent_id === selectedAgentId)
    )

    return (
      <div className="city-panel">
        <div className="cp-header">
          <button className="cp-back-btn" onClick={goBack}>返回</button>
          <h2>{agent.name}</h2>
        </div>

        <div className="cp-agent-detail">
          <h3>{agent.name}</h3>
          <div className="cp-status-bars">
            <div className="cp-status-row">
              <span className="cp-status-label">饱腹度</span>
              <div className="cp-status-track">
                <div
                  className={`cp-status-fill ${barColor(agent.satiety)}`}
                  style={{ width: `${agent.satiety}%` }}
                />
              </div>
              <span className="cp-status-value">{agent.satiety}</span>
            </div>
            <div className="cp-status-row">
              <span className="cp-status-label">心情</span>
              <div className="cp-status-track">
                <div
                  className={`cp-status-fill ${barColor(agent.mood)}`}
                  style={{ width: `${agent.mood}%` }}
                />
              </div>
              <span className="cp-status-value">{agent.mood}</span>
            </div>
            <div className="cp-status-row">
              <span className="cp-status-label">体力</span>
              <div className="cp-status-track">
                <div
                  className={`cp-status-fill ${barColor(agent.stamina)}`}
                  style={{ width: `${agent.stamina}%` }}
                />
              </div>
              <span className="cp-status-value">{agent.stamina}</span>
            </div>
          </div>

          {/* 个人资源 */}
          {agent.resources && agent.resources.length > 0 && (
            <div className="cp-agent-resources">
              {agent.resources.map(r => (
                <span key={r.resource_type} className="cp-agent-res-item">
                  {RESOURCE_ICONS[r.resource_type] ?? '📦'} {RESOURCE_NAMES[r.resource_type] ?? r.resource_type}: {r.quantity}
                </span>
              ))}
            </div>
          )}

          <div className="cp-agent-work">
            当前工作: {workBuilding
              ? `${workBuilding.name} (${BUILDING_ICONS[workBuilding.building_type] ?? workBuilding.building_type})`
              : '无'}
          </div>

          <button
            className="cp-eat-btn"
            onClick={handleEat}
            disabled={eating}
          >
            {eating ? '进食中...' : '进食'}
          </button>

          {eatMsg && <div className="cp-message success">{eatMsg}</div>}
          {eatErr && <div className="cp-message error">{eatErr}</div>}
        </div>
      </div>
    )
  }

  return <div className="city-panel"><div className="am-empty">加载中...</div></div>
}

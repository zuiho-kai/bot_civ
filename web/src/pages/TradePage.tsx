import { useState, useEffect, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { fetchCityOverview, transferResource, fetchMarketOrders, createMarketOrder, acceptMarketOrder, cancelMarketOrder, fetchTradeLogs } from '../api'
import { useWebSocket } from '../hooks/useWebSocket'
import type { CityAgentStatus, WsIncoming, MarketOrder, TradeLog } from '../types'
import './TradePage.css'

interface TransferLog {
  id: number
  fromName: string
  toName: string
  resourceType: string
  quantity: number
  time: string
}

let logIdCounter = 0

export function TradePage() {
  const [agents, setAgents] = useState<CityAgentStatus[]>([])
  const [fromId, setFromId] = useState<number | ''>('')
  const [toId, setToId] = useState<number | ''>('')
  const [resourceType, setResourceType] = useState('flour')
  const [quantity, setQuantity] = useState<number | ''>('')
  const [submitting, setSubmitting] = useState(false)
  const [message, setMessage] = useState<{ text: string; ok: boolean } | null>(null)
  const [history, setHistory] = useState<TransferLog[]>([])

  // 交易市场状态
  const [orders, setOrders] = useState<MarketOrder[]>([])
  const [tradeLogs, setTradeLogs] = useState<TradeLog[]>([])
  const [sellerId, setSellerId] = useState<number | ''>('')
  const [sellType, setSellType] = useState('flour')
  const [sellAmount, setSellAmount] = useState<number | ''>('')
  const [buyType, setBuyType] = useState('flour')
  const [buyAmount, setBuyAmount] = useState<number | ''>('')
  const [orderSubmitting, setOrderSubmitting] = useState(false)
  const [orderMsg, setOrderMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [acceptBuyerId, setAcceptBuyerId] = useState<number | ''>('')
  const [acceptRatio, setAcceptRatio] = useState<number>(1.0)

  const loadAgents = useCallback(async () => {
    try {
      const data = await fetchCityOverview('长安')
      setAgents(data.agents ?? [])
    } catch {
      /* ignore */
    }
  }, [])

  const loadOrders = useCallback(async () => {
    try {
      const data = await fetchMarketOrders(['open', 'partial'])
      setOrders(data)
    } catch {
      /* ignore */
    }
  }, [])

  const loadTradeLogs = useCallback(async () => {
    try {
      const data = await fetchTradeLogs(20)
      setTradeLogs(data)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    loadAgents()
    loadOrders()
    loadTradeLogs()
  }, [loadAgents, loadOrders, loadTradeLogs])

  // WebSocket: 监听 resource_transferred 事件
  const handleWs = useCallback((msg: WsIncoming) => {
    if (msg.type === 'system_event' && msg.data.event === 'resource_transferred') {
      const d = msg.data
      setHistory(prev => {
        const entry: TransferLog = {
          id: ++logIdCounter,
          fromName: d.from_agent_name ?? `Agent#${d.from_agent_id}`,
          toName: d.to_agent_name ?? `Agent#${d.to_agent_id}`,
          resourceType: d.resource_type ?? '?',
          quantity: d.quantity ?? 0,
          time: new Date(d.timestamp).toLocaleTimeString(),
        }
        const next = [entry, ...prev]
        return next.length > 50 ? next.slice(0, 50) : next
      })
      loadAgents()
      loadOrders()
      loadTradeLogs()
    }
  }, [loadAgents, loadOrders, loadTradeLogs])

  useWebSocket(handleWs)

  const handleSubmit = async () => {
    if (fromId === '' || toId === '' || !quantity || quantity <= 0) return
    if (fromId === toId) {
      setMessage({ text: '不能转赠给自己', ok: false })
      return
    }
    setSubmitting(true)
    setMessage(null)
    try {
      const res = await transferResource(fromId, toId, resourceType, quantity)
      setMessage({ text: res.reason, ok: res.ok })
      setTimeout(() => setMessage(null), 3000)
      if (res.ok) {
        setQuantity('')
        loadAgents()
      }
    } catch (e) {
      setMessage({ text: String(e), ok: false })
      setTimeout(() => setMessage(null), 3000)
    } finally {
      setSubmitting(false)
    }
  }

  const handleCreateOrder = async () => {
    if (sellerId === '' || !sellAmount || sellAmount <= 0 || !buyAmount || buyAmount <= 0) return
    if (sellType === buyType) {
      setOrderMsg({ text: '卖出和求购不能是同一种资源', ok: false })
      return
    }
    setOrderSubmitting(true)
    setOrderMsg(null)
    try {
      const res = await createMarketOrder({
        seller_id: sellerId,
        sell_type: sellType,
        sell_amount: sellAmount,
        buy_type: buyType,
        buy_amount: buyAmount,
      })
      setOrderMsg({ text: res.reason ?? '挂单成功', ok: res.ok })
      setTimeout(() => setOrderMsg(null), 3000)
      if (res.ok) {
        setSellAmount('')
        setBuyAmount('')
        loadOrders()
        loadAgents()
      }
    } catch (e) {
      setOrderMsg({ text: String(e), ok: false })
      setTimeout(() => setOrderMsg(null), 3000)
    } finally {
      setOrderSubmitting(false)
    }
  }

  const handleAccept = async (orderId: number) => {
    if (acceptBuyerId === '') return
    try {
      const res = await acceptMarketOrder(orderId, acceptBuyerId, acceptRatio)
      setOrderMsg({ text: res.reason ?? '接单成功', ok: res.ok })
      setTimeout(() => setOrderMsg(null), 3000)
      if (res.ok) {
        setAcceptRatio(1.0)
        loadOrders()
        loadAgents()
        loadTradeLogs()
      }
    } catch (e) {
      setOrderMsg({ text: String(e), ok: false })
      setTimeout(() => setOrderMsg(null), 3000)
    }
  }

  const handleCancel = async (orderId: number, orderSellerId: number) => {
    if (!confirm('确认撤销此挂单？')) return
    try {
      const res = await cancelMarketOrder(orderId, orderSellerId)
      setOrderMsg({ text: res.reason ?? '撤单成功', ok: res.ok })
      setTimeout(() => setOrderMsg(null), 3000)
      if (res.ok) {
        loadOrders()
        loadAgents()
      }
    } catch (e) {
      setOrderMsg({ text: String(e), ok: false })
      setTimeout(() => setOrderMsg(null), 3000)
    }
  }

  // 收集所有出现过的资源类型
  const resourceTypes = [...new Set(
    agents.flatMap(a => a.resources.map(r => r.resource_type))
  )]
  if (!resourceTypes.includes('flour')) resourceTypes.unshift('flour')

  const agentName = (id: number) => agents.find(a => a.id === id)?.name ?? `#${id}`

  return (
    <div className="trade-page">
      <div className="tp-header">
        <Link to="/" className="tp-back-btn" aria-label="返回主界面">← 返回</Link>
        <h2>资源交易面板</h2>
      </div>

      <div className="tp-section-title">居民资源概览</div>
      <div className="tp-agent-resources">
        {agents.map(a => (
          <div key={a.id} className="tp-agent-row">
            <span className="tp-agent-name">{a.name}</span>
            <span className="tp-agent-res">
              {a.resources.length > 0
                ? a.resources.map(r => `${r.resource_type}=${r.quantity}`).join(', ')
                : '无资源'}
            </span>
          </div>
        ))}
      </div>

      <div className="tp-section-title">转赠资源</div>
      <div className="tp-form" role="form" aria-label="资源转赠表单">
        <label>
          发送方
          <select
            value={fromId}
            onChange={e => setFromId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">选择居民</option>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label>
          接收方
          <select
            value={toId}
            onChange={e => setToId(e.target.value ? Number(e.target.value) : '')}
          >
            <option value="">选择居民</option>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label>
          资源类型
          <select value={resourceType} onChange={e => setResourceType(e.target.value)}>
            {resourceTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          数量
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={e => setQuantity(e.target.value ? Number(e.target.value) : '')}
          />
        </label>
        <div className="tp-submit-row">
          <button
            className="tp-submit-btn"
            disabled={submitting || fromId === '' || toId === '' || !quantity}
            onClick={handleSubmit}
          >
            {submitting ? '转赠中...' : '转赠'}
          </button>
          {message && (
            <span className={`tp-message ${message.ok ? 'success' : 'error'}`}>
              {message.text}
            </span>
          )}
        </div>
      </div>

      <div className="tp-section-title">转赠历史（实时）</div>
      <div className="tp-history" aria-live="polite">
        {history.length === 0 ? (
          <div className="tp-history-empty">暂无转赠记录</div>
        ) : (
          history.map(h => (
            <div key={h.id} className="tp-history-item">
              <span className="tp-history-time">{h.time}</span>
              <span>{h.fromName} → {h.toName}: {h.quantity} {h.resourceType}</span>
            </div>
          ))
        )}
      </div>

      {/* ── 交易市场 ── */}
      <div className="tp-section-title tp-market-title">交易市场</div>

      <div className="tp-form" role="form" aria-label="挂单表单">
        <label className="tp-full-row">
          卖家
          <select value={sellerId} onChange={e => setSellerId(e.target.value ? Number(e.target.value) : '')}>
            <option value="">选择居民</option>
            {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
          </select>
        </label>
        <label>
          卖出资源
          <select value={sellType} onChange={e => setSellType(e.target.value)}>
            {resourceTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          卖出数量
          <input type="number" min={0.01} step={0.01} value={sellAmount}
            onChange={e => setSellAmount(e.target.value ? Number(e.target.value) : '')} />
        </label>
        <label>
          求购资源
          <select value={buyType} onChange={e => setBuyType(e.target.value)}>
            {resourceTypes.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label>
          求购数量
          <input type="number" min={0.01} step={0.01} value={buyAmount}
            onChange={e => setBuyAmount(e.target.value ? Number(e.target.value) : '')} />
        </label>
        <div className="tp-submit-row">
          <button className="tp-submit-btn" disabled={orderSubmitting || sellerId === '' || !sellAmount || !buyAmount}
            onClick={handleCreateOrder}>
            {orderSubmitting ? '挂单中...' : '挂单'}
          </button>
          {orderMsg && (
            <span className={`tp-message ${orderMsg.ok ? 'success' : 'error'}`}>{orderMsg.text}</span>
          )}
        </div>
      </div>

      <div className="tp-section-title">当前挂单</div>
      <div className="tp-orders">
        {orders.length === 0 ? (
          <div className="tp-history-empty">暂无挂单</div>
        ) : (
          <>
            <div className="tp-order-actions-bar">
              <label>
                买家
                <select value={acceptBuyerId} onChange={e => setAcceptBuyerId(e.target.value ? Number(e.target.value) : '')}>
                  <option value="">选择居民</option>
                  {agents.map(a => <option key={a.id} value={a.id}>{a.name}</option>)}
                </select>
              </label>
              <label>
                购买比例
                <input type="number" min={0.01} max={1} step={0.01} value={acceptRatio}
                  onChange={e => setAcceptRatio(Number(e.target.value) || 1)} />
              </label>
            </div>
            {orders.map(o => (
              <div key={o.id} className="tp-order-card">
                <div className="tp-order-info">
                  <span className="tp-order-seller">{o.seller_name ?? agentName(o.seller_id)}</span>
                  <span className="tp-order-detail">
                    卖 {o.remain_sell_amount}/{o.sell_amount} {o.sell_type} → 求 {o.remain_buy_amount}/{o.buy_amount} {o.buy_type}
                  </span>
                  <span className={`tp-order-status tp-status-${o.status}`}>{o.status}</span>
                </div>
                <div className="tp-order-btns">
                  <button className="tp-btn-accept" disabled={acceptBuyerId === ''}
                    onClick={() => handleAccept(o.id)}>接单</button>
                  <button className="tp-btn-cancel"
                    onClick={() => handleCancel(o.id, o.seller_id)}>撤单</button>
                </div>
              </div>
            ))}
          </>
        )}
      </div>

      <div className="tp-section-title">成交记录</div>
      <div className="tp-history">
        {tradeLogs.length === 0 ? (
          <div className="tp-history-empty">暂无成交记录</div>
        ) : (
          tradeLogs.map(t => (
            <div key={t.id} className="tp-history-item">
              <span className="tp-history-time">{new Date(t.created_at).toLocaleTimeString()}</span>
              <span>
                {agentName(t.seller_id)} → {agentName(t.buyer_id)}: {t.sell_amount} {t.sell_type} ↔ {t.buy_amount} {t.buy_type}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  )
}

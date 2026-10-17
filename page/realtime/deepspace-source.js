/*
 * Real-time notices from the DeepSpace bridge (planit-realtime), for plain JS.
 *
 * DeepSpace's own client is React-only, so this speaks its record protocol
 * directly over one WebSocket:
 *   - connect anonymously to /ws/<scope>  (notices are IDs only, safe to read)
 *   - send core.subscribe for the `events` collection
 *   - core.query_result  = subscribed (existing events are ignored)
 *   - core.record_change = a new notice -> onEvent(notice)
 *
 * Shape matches the source the crew adapter expects:
 *   const source = createDeepSpaceSource({ baseURL, appId })
 *   const unsubscribe = await source.subscribe({ onEvent, onConnection, onError })
 *
 * Reconnecting is the caller's job (the crew adapter already retries).
 */

const SUBSCRIBE = 'core.subscribe'
const QUERY_RESULT = 'core.query_result'
const RECORD_CHANGE = 'core.record_change'
const ERROR = 'core.error'

function toNotice(data) {
  const notice = { type: data.type }
  for (const key of ['site_id', 'alert_id', 'report_id', 'clear_at', 'sent_at']) {
    if (data[key] !== undefined && data[key] !== null) notice[key] = data[key]
  }
  if (typeof data.site_ids === 'string') {
    try { notice.site_ids = JSON.parse(data.site_ids) } catch { /* malformed list: leave it out */ }
  }
  return notice
}

export function createDeepSpaceSource({ baseURL, appId, WebSocketImpl = globalThis.WebSocket }) {
  const scope = `app:${appId}`
  const wsURL = baseURL.replace(/^http/, 'ws').replace(/\/$/, '') + `/ws/${encodeURIComponent(scope)}`

  return {
    subscribe({ onEvent, onConnection = () => {}, onError = () => {} }) {
      const ws = new WebSocketImpl(wsURL)
      const subscriptionId = `planit-events-${Math.random().toString(36).slice(2)}`
      let closed = false

      ws.addEventListener('open', () => {
        ws.send(JSON.stringify({
          type: SUBSCRIBE,
          payload: {
            subscriptionId,
            query: { collection: 'events', orderBy: 'sent_at', orderDir: 'desc', limit: 1 },
          },
        }))
      })

      ws.addEventListener('message', (msg) => {
        if (typeof msg.data !== 'string') return // binary frames are Yjs traffic, not ours
        let message
        try { message = JSON.parse(msg.data) } catch { return }
        const { type, payload } = message
        if (type === QUERY_RESULT && payload?.subscriptionId === subscriptionId) {
          onConnection(true)
        } else if (type === RECORD_CHANGE && payload?.collection === 'events' && payload.changeType === 'create') {
          const data = payload.record?.data
          if (data && typeof data.type === 'string') onEvent(toNotice(data))
        } else if (type === ERROR) {
          onError(new Error(payload?.error || 'DeepSpace error'))
        }
      })

      ws.addEventListener('close', () => { if (!closed) onConnection(false) })
      ws.addEventListener('error', () => onError(new Error('DeepSpace connection error')))

      return () => { closed = true; ws.close() }
    },
  }
}

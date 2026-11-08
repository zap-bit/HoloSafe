import { get, set } from 'idb-keyval'
import { useStore } from './store'
import type { Snapshot } from './types'

const CACHE_KEY = 'holosafe:snapshot'
let started = false

/** One WebSocket per tab feeding the zustand store. Snapshots are cached to IndexedDB
 *  so the UI keeps rendering the last known world state if the link drops. */
export function startLink() {
  if (started) return
  started = true
  get<Snapshot>(CACHE_KEY).then((s) => {
    if (s && !useStore.getState().snap) useStore.getState().setSnap(s, true)
  }).catch(() => {})

  let retry = 0
  const open = () => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    // Hosted: VITE_WS_URL points straight at the backend (e.g. wss://holosafe-api.onrender.com/ws),
    // because Vercel rewrites can't proxy WebSockets. Local dev: same host, proxied by Vite.
    const ws = new WebSocket(import.meta.env.VITE_WS_URL || `${proto}://${location.host}/ws`)
    ws.onopen = () => { retry = 0; useStore.getState().setLink('live') }
    ws.onmessage = (ev) => {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'snapshot') {
        useStore.getState().setSnap(msg.data)
        set(CACHE_KEY, msg.data).catch(() => {})
      } else if (msg.type === 'event' && msg.kind === 'edge_pulse') {
        useStore.getState().pulse(msg.data.edge_id)
      }
    }
    ws.onclose = () => {
      useStore.getState().setLink('lost')
      setTimeout(open, Math.min(4000, 500 * 2 ** retry++))
    }
    ws.onerror = () => ws.close()
  }
  open()
}

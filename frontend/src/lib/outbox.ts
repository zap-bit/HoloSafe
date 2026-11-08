import { create } from 'zustand'
import { get, set } from 'idb-keyval'
import { useEffect } from 'react'
import { useStore } from './store'
import { api } from './api'

/** Per-device outgoing report queue (IndexedDB) + simulated peer-to-peer mesh (BroadcastChannel).
 *  Offline: reports are queued and gossiped to nearby "devices" (other tabs / the Device B panel).
 *  Back online: every device flushes what it holds; the server dedupes by id, so double-sync is harmless. */
export interface OutItem {
  local_id: string; device: string; origin: string; text: string; node_id: string; kind: string
  status: 'queued' | 'sending' | 'sent'; server_id?: string; created_at: string; via_mesh?: boolean
}

interface OB { boxes: Record<string, OutItem[]>; loaded: Record<string, boolean>; put: (dev: string, items: OutItem[]) => void }
const useOB = create<OB>((setS) => ({
  boxes: {}, loaded: {},
  put: (dev, items) => setS((s) => ({ boxes: { ...s.boxes, [dev]: items }, loaded: { ...s.loaded, [dev]: true } })),
}))

const key = (dev: string) => `holosafe:outbox:${dev}`
const save = (dev: string, items: OutItem[]) => { useOB.getState().put(dev, items); set(key(dev), items).catch(() => {}) }
const box = (dev: string) => useOB.getState().boxes[dev] ?? []

export function deviceId(): string {
  try {
    let d = localStorage.getItem('holosafe:device')
    if (!d) { d = 'phone-' + Math.random().toString(36).slice(2, 6); localStorage.setItem('holosafe:device', d) }
    return d
  } catch { return 'phone-anon' }
}

const isOffline = () => { const s = useStore.getState(); return !!s.snap?.offline || s.link !== 'live' }

let chan: BroadcastChannel | null = null
const devices = new Set<string>()
function mesh(): BroadcastChannel | null {
  if (chan || typeof BroadcastChannel === 'undefined') return chan
  chan = new BroadcastChannel('holosafe-mesh')
  chan.onmessage = (ev) => receive(ev.data)
  return chan
}

function receive(msg: any) {
  if (msg?.type === 'report') {
    for (const dev of devices) {
      if (dev === msg.item.device) continue
      if (box(dev).some((x) => x.local_id === msg.item.local_id)) continue
      save(dev, [{ ...msg.item, device: dev, via_mesh: true }, ...box(dev)])
    }
  } else if (msg?.type === 'synced') {
    for (const dev of devices) save(dev, box(dev).map((x) => (msg.ids.includes(x.local_id) ? { ...x, status: 'sent', server_id: x.local_id } : x)))
  }
}

function gossip(item: OutItem, local = true) {
  if (local) receive({ type: 'report', item }) // devices in this same tab (Device B panel)
  mesh()?.postMessage({ type: 'report', item })
}

export async function submitReport(r: { text: string; node_id: string; kind: string; device: string }) {
  const item: OutItem = { local_id: 'REP-' + Math.random().toString(36).slice(2, 8), device: r.device, origin: r.device, text: r.text,
    node_id: r.node_id, kind: r.kind, status: 'queued', created_at: new Date().toISOString() }
  if (isOffline()) {
    save(r.device, [item, ...box(r.device)])
    gossip(item)
    return { queued: true }
  }
  save(r.device, [{ ...item, status: 'sending' }, ...box(r.device)])
  try {
    const res = await api.post('/api/report', { id: item.local_id, text: r.text, node_id: r.node_id, kind: r.kind, device: r.device })
    save(r.device, box(r.device).map((x) => (x.local_id === item.local_id ? { ...x, status: 'sent', server_id: res.report_id } : x)))
    return { queued: false }
  } catch {
    save(r.device, box(r.device).map((x) => (x.local_id === item.local_id ? { ...x, status: 'queued' } : x)))
    gossip(item)
    return { queued: true }
  }
}

let flushing = false
export async function flushAll() {
  if (flushing || isOffline()) return
  const pending = [...devices].flatMap((d) => box(d).filter((x) => x.status === 'queued').map((x) => ({ d, x })))
  const uniq = [...new Map(pending.map((p) => [p.x.local_id, p])).values()]
  if (!uniq.length) return
  flushing = true
  useStore.getState().setSyncing(uniq.length)
  const done: string[] = []
  for (const { x } of uniq) {
    try {
      await api.post('/api/report', { id: x.local_id, text: x.text, node_id: x.node_id, kind: x.kind, device: x.via_mesh ? `${x.origin} via mesh` : x.origin })
      done.push(x.local_id)
      for (const d of devices) save(d, box(d).map((y) => (y.local_id === x.local_id ? { ...y, status: 'sent', server_id: x.local_id } : y)))
      await new Promise((r) => setTimeout(r, 350))
    } catch { /* stays queued */ }
  }
  mesh()?.postMessage({ type: 'synced', ids: done })
  setTimeout(() => useStore.getState().setSyncing(0), 1600)
  flushing = false
}

// flush whenever connectivity comes back
let wasOffline = false
useStore.subscribe((s) => {
  const off = !!s.snap?.offline || s.link !== 'live'
  if (wasOffline && !off) setTimeout(flushAll, 400)
  wasOffline = off
})

export function useOutbox(dev: string): OutItem[] {
  const items = useOB((s) => s.boxes[dev])
  useEffect(() => {
    devices.add(dev)
    mesh()
    if (!useOB.getState().loaded[dev]) get<OutItem[]>(key(dev)).then((v) => useOB.getState().put(dev, v ?? [])).catch(() => useOB.getState().put(dev, []))
    return () => { devices.delete(dev) }
  }, [dev])
  return items ?? []
}

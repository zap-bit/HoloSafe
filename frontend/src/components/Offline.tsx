import { useState } from 'react'
import { createPortal } from 'react-dom'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import { useOutbox } from '../lib/outbox'
import ReportPage from '../pages/Report'

export function OfflineToggle() {
  const snap = useStore((s) => s.snap)
  const off = !!snap?.offline
  const queuedMsgs = snap?.messages.filter((m) => m.status === 'queued').length ?? 0
  return (
    <div className="flex items-center gap-2">
      {queuedMsgs > 0 && <span className="chip animate-pulse text-amber">✉ {queuedMsgs} queued</span>}
      <button className={`btn ${off ? 'btn-lime' : 'btn-magenta'}`} onClick={() => api.post('/api/offline', { offline: !off })}>
        {off ? '⟲ Reconnect' : '⦸ Offline'}
      </button>
    </div>
  )
}

export const MESH_DEVICE = 'mesh-node-B'

export function MeshDevice({ onClose }: { onClose: () => void }) {
  const items = useOutbox(MESH_DEVICE)
  const heard = items.filter((x) => x.via_mesh)
  return (
    <div className="panel slidein pointer-events-auto absolute right-3 bottom-3 z-30 flex max-h-[calc(100%-24px)] w-[340px] flex-col p-2">
      <div className="flex items-center justify-between px-1">
        <span className="panel-title">Simulated device B · mesh node</span>
        <button className="font-mono text-xs text-dim hover:text-white" onClick={onClose}>✕</button>
      </div>
      <div className="px-1 font-mono text-[10px] text-dim">Peer-to-peer via BroadcastChannel. Open /report in another tab as device A.</div>
      <div className="mt-1 border border-[#9fd8ff]/30 p-1.5">
        <div className="font-mono text-[10px] tracking-widest text-[#9fd8ff]">HEARD VIA MESH ({heard.length})</div>
        {!heard.length && <div className="font-mono text-[10px] text-dim">nothing relayed yet</div>}
        {heard.slice(0, 4).map((h) => (
          <div key={h.local_id} className="flex gap-2 text-[11px]">
            <span className={`chip shrink-0 ${h.status === 'queued' ? 'text-amber' : 'text-lime'}`}>{h.status === 'queued' ? 'relaying' : 'synced'}</span>
            <span className="truncate text-white/70">{h.origin}: {h.text}</span>
          </div>
        ))}
      </div>
      <div className="scroll-thin min-h-0 flex-1 overflow-y-auto"><ReportPage embedded device={MESH_DEVICE} /></div>
    </div>
  )
}

export function MeshButton() {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button className="btn" onClick={() => setOpen((o) => !o)}>⌬ Device B</button>
      {/* Portal to <body>: the header uses backdrop-filter, which would otherwise trap this fixed overlay inside the header box. */}
      {open && createPortal(
        <div className="pointer-events-none fixed inset-x-0 top-14 bottom-0 z-30"><div className="relative h-full"><MeshDevice onClose={() => setOpen(false)} /></div></div>,
        document.body,
      )}
    </>
  )
}

export function SyncOverlay() {
  const n = useStore((s) => s.syncing)
  if (!n) return null
  return (
    <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center">
      <div className="panel slidein flex flex-col items-center gap-2 px-8 py-5">
        <div className="flex gap-1">
          {Array.from({ length: 12 }, (_, i) => (
            <span key={i} className="h-6 w-1.5 bg-lime shadow-[0_0_10px_#00ffa3]" style={{ animation: `flicker 0.6s ${i * 0.05}s infinite` }} />
          ))}
        </div>
        <div className="font-display text-sm tracking-[0.4em] text-lime glow-text">LINK RESTORED · SYNCING</div>
        <div className="font-mono text-[11px] text-white/70">{n} queued report{n > 1 ? 's' : ''} → command center → Report Agent</div>
      </div>
    </div>
  )
}

export function LinkBanner() {
  const link = useStore((s) => s.link)
  const fromCache = useStore((s) => s.fromCache)
  const off = useStore((s) => s.snap?.offline)
  if (link === 'live' && !off) return null
  const txt = link !== 'live'
    ? `COMMAND LINK LOST — rendering ${fromCache ? 'cached snapshot (IndexedDB)' : 'last known state'} · reconnecting…`
    : 'OFFLINE MODE — internet down: agents on local MOCK, outgoing messages QUEUED, civilian reports relay over mesh'
  return (
    <div className="pointer-events-none absolute top-0 right-0 left-0 z-20 bg-gradient-to-r from-amber/0 via-amber/25 to-amber/0 py-1 text-center font-mono text-[11px] tracking-widest text-amber">
      {txt}
    </div>
  )
}

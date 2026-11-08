import { useEffect, useMemo, useState } from 'react'
import { useStore } from '../lib/store'
import { submitReport, useOutbox, deviceId } from '../lib/outbox'
import Logo from '../components/Logo'
import { SEVERITY } from '../lib/colors'
import { SyncOverlay } from '../components/Offline'

type Cat = 'blocked_route' | 'hazard' | 'distress'
const CATS: { id: Cat; label: string; icon: string; color: string; quick: string[] }[] = [
  { id: 'blocked_route', label: 'Blocked route', icon: '⛔', color: '#ffb020', quick: ['Stairwell 1 blocked by debris', 'Corridor caved in, can\'t get through', 'Exit door jammed shut'] },
  { id: 'hazard', label: 'Hazard', icon: '⚠', color: '#ff8a1f', quick: ['Smell of gas', 'Smoke coming from the floor below', 'Sparking power lines'] },
  { id: 'distress', label: 'Distress', icon: '✚', color: '#ff2a4d', quick: ['I am trapped and can\'t get out', 'Someone is injured and bleeding', 'Elderly neighbour can\'t walk down stairs'] },
]

export default function ReportPage({ embedded = false, device }: { embedded?: boolean; device?: string }) {
  const snap = useStore((s) => s.snap)
  const link = useStore((s) => s.link)
  const dev = device ?? deviceId()
  const outbox = useOutbox(dev)
  const [cat, setCat] = useState<Cat>('blocked_route')
  const [building, setBuilding] = useState<string>('B1')
  const [floor, setFloor] = useState<number>(2)
  const [node, setNode] = useState<string>('B1-F2-S1')
  const [text, setText] = useState('Stairwell 1 blocked by debris')
  const [flash, setFlash] = useState<string | null>(null)

  const b = snap?.buildings.find((x) => x.id === building)
  const nodes = useMemo(() => {
    if (!snap) return []
    if (building === 'street') return snap.nodes.filter((n) => n.kind === 'street')
    return snap.nodes.filter((n) => n.building_id === building && (n.floor === floor || (n.kind === 'exit' && floor === 1)))
      .sort((a, c) => ['stair', 'exit', 'corridor', 'room'].indexOf(a.kind) - ['stair', 'exit', 'corridor', 'room'].indexOf(c.kind) || a.id.localeCompare(c.id, undefined, { numeric: true }))
  }, [snap, building, floor])
  useEffect(() => { if (nodes.length && !nodes.find((n) => n.id === node)) setNode(nodes[0].id) }, [nodes, node])

  const offline = !!snap?.offline || link !== 'live'
  const send = async () => {
    if (!text.trim() || !node) return
    const r = await submitReport({ text: text.trim(), node_id: node, kind: cat, device: dev })
    setFlash(r.queued ? 'QUEUED — no network. Will relay via mesh & sync when back online.' : 'SENT — HoloSafe agents are processing your report.')
    setTimeout(() => setFlash(null), 3500)
  }
  const c = CATS.find((x) => x.id === cat)!

  const body = (
    <div className={`relative mx-auto flex w-full max-w-[420px] flex-col gap-3 ${embedded ? 'p-2' : 'min-h-full p-4'}`}>
      <div className="flex items-center gap-3">
        <Logo className="h-10 w-10 drop-shadow-[0_0_8px_#ff8a1f]" />
        <div className="leading-tight">
          <div className="font-display text-base font-black tracking-[0.3em] text-white [text-shadow:0_0_10px_#19e6ff]">HOLOSAFE</div>
          <div className="font-mono text-[10px] tracking-[0.25em] text-cyan/70">CIVILIAN LINK · {dev}</div>
        </div>
        <span className="chip ml-auto" style={{ color: offline ? '#ffb020' : '#00ffa3' }}>
          <span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: offline ? '#ffb020' : '#00ffa3' }} />
          {offline ? 'NO NETWORK · MESH' : 'CONNECTED'}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2">
        {CATS.map((x) => (
          <button key={x.id} onClick={() => { setCat(x.id); setText(x.quick[0]) }}
            className="panel flex flex-col items-center gap-1 py-3 transition"
            style={{ borderColor: cat === x.id ? x.color : undefined, boxShadow: cat === x.id ? `inset 0 0 24px ${x.color}44, 0 0 16px ${x.color}55` : undefined }}>
            <span className="text-2xl" style={{ color: x.color, textShadow: `0 0 12px ${x.color}` }}>{x.icon}</span>
            <span className="font-display text-[9px] tracking-[0.18em] text-white uppercase">{x.label}</span>
          </button>
        ))}
      </div>

      <div className="panel space-y-2 p-3">
        <div className="panel-title">Where are you?</div>
        <div className="flex flex-wrap gap-1.5">
          {snap?.buildings.map((x) => (
            <button key={x.id} className={`btn !px-2 !py-1.5 !text-[9px] ${building === x.id ? '!bg-cyan/25 !text-white' : ''}`}
              onClick={() => { setBuilding(x.id); setFloor(1) }}>{x.name}</button>
          ))}
          <button className={`btn !px-2 !py-1.5 !text-[9px] ${building === 'street' ? '!bg-cyan/25 !text-white' : ''}`} onClick={() => setBuilding('street')}>Outside</button>
        </div>
        {b && (
          <div className="flex items-center gap-2">
            <span className="font-mono text-[11px] text-dim">FLOOR</span>
            {Array.from({ length: b.floors }, (_, i) => i + 1).map((f) => (
              <button key={f} className={`btn !px-3 !py-1 ${floor === f ? '!bg-cyan/25 !text-white' : ''}`} onClick={() => setFloor(f)}>{f}</button>
            ))}
          </div>
        )}
        <select value={node} onChange={(e) => setNode(e.target.value)}
          className="w-full border border-cyan/30 bg-black/60 px-2 py-2 font-mono text-[13px] text-cyan outline-none">
          {nodes.map((n) => <option key={n.id} value={n.id}>{n.kind === 'stair' ? '▤ ' : n.kind === 'exit' ? '⇥ ' : n.kind === 'room' ? '□ ' : '· '}{n.label}</option>)}
        </select>
      </div>

      <div className="panel space-y-2 p-3">
        <div className="panel-title">What's happening?</div>
        <div className="flex flex-wrap gap-1.5">
          {c.quick.map((q) => (
            <button key={q} onClick={() => setText(q)} className="border border-white/15 px-2 py-1 text-[11px] text-white/75 hover:border-white/40">{q}</button>
          ))}
        </div>
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
          className="w-full resize-none border border-cyan/30 bg-black/60 p-2 text-[14px] text-white outline-none focus:border-cyan" />
      </div>

      <button onClick={send} className="btn btn-red !py-4 !text-sm" disabled={!text.trim()}>
        {offline ? '⟲ Queue report (offline)' : '▲ Send report'}
      </button>
      {flash && <div className="slidein border border-lime/40 bg-lime/10 p-2 text-center font-mono text-[11px] text-lime">{flash}</div>}

      {outbox.length > 0 && (
        <div className="panel p-3">
          <div className="panel-title mb-1">Your reports</div>
          <div className="space-y-1">
            {outbox.slice(0, 5).map((r) => {
              const server = snap?.reports.find((x) => x.id === r.server_id)
              const inc = server?.incident_id ? snap?.incidents.find((i) => i.id === server.incident_id) : null
              const st = r.status === 'queued' ? 'QUEUED' : server?.status === 'processing' ? 'AGENTS PROCESSING' : inc ? `INCIDENT · ${inc.severity}` : 'RECEIVED'
              const col = r.status === 'queued' ? '#ffb020' : inc ? SEVERITY[inc.severity] : '#00ffa3'
              return (
                <div key={r.local_id} className="flex items-center gap-2 text-[11px]">
                  <span className="chip shrink-0" style={{ color: col }}>{st}</span>
                  <span className="truncate text-white/70">{r.text}</span>
                  {r.via_mesh && <span className="chip text-[#9fd8ff]">mesh</span>}
                </div>
              )
            })}
          </div>
        </div>
      )}
      {!embedded && <div className="text-center font-mono text-[9px] text-dim">Your location and report go only to the HoloSafe command center.</div>}
    </div>
  )
  if (embedded) return body
  return <div className="scanlines h-full overflow-y-auto bg-[radial-gradient(ellipse_at_top,#0a1e2e,#04060b_70%)]">{body}<SyncOverlay /></div>
}

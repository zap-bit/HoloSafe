import { useStore } from '../lib/store'
import { SEVERITY } from '../lib/colors'
import { ago, placeOf } from '../lib/util'

export default function IncidentHistory() {
  const snap = useStore((s) => s.snap)
  if (!snap) return null
  return (
    <div className="panel flex max-h-[34%] shrink-0 flex-col p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="panel-title">Incident history · reports</span>
        <span className="font-mono text-[10px] text-dim">{snap.reports.length} received</span>
      </div>
      <div className="scroll-thin min-h-0 space-y-1 overflow-y-auto pr-1">
        {!snap.reports.length && <div className="py-2 text-center font-mono text-[11px] text-dim">No reports yet. Phones submit at /report</div>}
        {snap.reports.map((r) => {
          const inc = r.incident_id ? snap.incidents.find((i) => i.id === r.incident_id) : null
          const col = r.status === 'processing' ? '#b366ff' : inc ? SEVERITY[inc.severity] : '#5b6b80'
          return (
            <div key={r.id} className="slidein flex gap-2 text-[11px] leading-snug">
              <span className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: col, boxShadow: `0 0 6px ${col}` }} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-white/80">“{r.text}”</div>
                <div className="truncate font-mono text-[10px] text-dim">
                  {r.device} · {placeOf(snap, r.node_id)} · {ago(r.created_at)} · <span style={{ color: col }}>{r.status === 'processing' ? 'AGENTS…' : inc ? `${inc.kind} ${inc.severity}` : r.status}</span>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

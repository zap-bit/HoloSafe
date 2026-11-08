import { useStore } from '../lib/store'
import { SEVERITY } from '../lib/colors'
import { ago, placeOf, SOURCE_ICON } from '../lib/util'
import { setView } from './ScenePane'

export default function TriageQueue() {
  const snap = useStore((s) => s.snap)
  if (!snap) return null
  const open = snap.incidents.filter((i) => i.severity !== 'resolved')
  const resolved = snap.incidents.filter((i) => i.severity === 'resolved')
  return (
    <div className="panel flex min-h-0 flex-1 flex-col p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="panel-title">Triage queue</span>
        <span className="font-mono text-[10px] text-dim">ranked by severity · isolation · vulnerability · confidence — not volume</span>
      </div>
      <div className="scroll-thin min-h-0 flex-1 space-y-1.5 overflow-y-auto pr-1">
        {!open.length && <div className="py-6 text-center font-mono text-xs text-dim">NO ACTIVE INCIDENTS</div>}
        {[...open, ...resolved].map((i) => {
          const c = SEVERITY[i.severity]
          const n = snap.nodes.find((x) => x.id === i.node_id)
          const person = i.person_id ? snap.people.find((p) => p.id === i.person_id) : null
          const resp = snap.responders.find((r) => r.assigned_incident_id === i.id)
          const pending = snap.approvals.find((a) => a.status === 'pending' && a.action === 'dispatch_responder' && a.payload.incident_id === i.id)
          return (
            <button key={i.id} className={`slidein relative block w-full border-l-2 bg-white/[0.025] px-2 py-1.5 text-left hover:bg-white/[0.06] ${i.severity === 'resolved' ? 'opacity-40' : ''}`}
              style={{ borderColor: c }} onClick={() => n?.building_id && setView({ focus_building: n.building_id, focus_floor: n.floor })}>
              <div className="flex items-baseline gap-2">
                <span className="font-display text-lg leading-none font-black" style={{ color: c, textShadow: `0 0 10px ${c}` }}>{i.rank ?? '–'}</span>
                <span className="chip" style={{ color: c }}>{i.severity}</span>
                <span className="font-display text-[11px] tracking-wider text-white uppercase">{i.kind.replace('_', ' ')}</span>
                <span className="ml-auto font-mono text-[10px] text-dim">{SOURCE_ICON[i.source]} {i.source} · {ago(i.created_at)}</span>
              </div>
              <div className="mt-0.5 truncate text-[12px] text-cyan/90">{placeOf(snap, i.node_id)}{person ? ` — ${person.name}` : ''}</div>
              <div className="truncate text-[11px] text-white/55">{i.description}</div>
              {i.rank_reason && <div className="mt-0.5 font-mono text-[10px] text-amber/80">{i.rank_reason}</div>}
              <div className="mt-1 flex items-center gap-2">
                <div className="h-1 flex-1 bg-white/10"><div className="h-full" style={{ width: `${i.confidence * 100}%`, background: c }} /></div>
                <span className="font-mono text-[10px] text-dim">conf {Math.round(i.confidence * 100)}%</span>
                {i.score != null && <span className="font-mono text-[10px] text-dim">score {i.score}</span>}
                {resp && <span className="chip text-magenta">{resp.name} {resp.status.replace('_', ' ')}</span>}
                {!resp && pending && <span className="chip text-magenta/70">dispatch pending</span>}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}

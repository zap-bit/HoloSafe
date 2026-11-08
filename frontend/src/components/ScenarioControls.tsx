import { useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'

export default function ScenarioControls() {
  const snap = useStore((s) => s.snap)
  const [hazard, setHazard] = useState('earthquake')
  const [pending, setPending] = useState(false)
  const hazards = snap?.hazards ?? []
  const go = async (fn: () => Promise<unknown>) => { setPending(true); try { await fn() } finally { setPending(false) } }
  return (
    <div className="flex items-center gap-2">
      <div className="flex">
        {hazards.map((h) => (
          <button key={h.id} title={h.description}
            className={`btn !px-3 ${hazard === h.id ? '!border-amber !bg-amber/20 !text-white' : '!text-dim'}`}
            onClick={() => setHazard(h.id)}>{h.id === 'earthquake' ? '◬ ' : '⌁ '}{h.id}</button>
        ))}
      </div>
      <button className="btn btn-red" disabled={pending || snap?.busy} onClick={() => go(() => api.post('/api/scenario/trigger', { hazard }))}>
        ▶ Trigger scenario
      </button>
      <button className="btn" disabled={pending} onClick={() => go(() => api.post('/api/scenario/reset'))}>↺ Reset</button>
    </div>
  )
}

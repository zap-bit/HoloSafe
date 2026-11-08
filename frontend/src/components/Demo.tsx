import { useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import { submitReport } from '../lib/outbox'
import { setView } from './ScenePane'

type Act = { label: string; run: () => Promise<unknown> | void }
interface Step { title: string; say: string; acts?: Act[] }

const approveFirst = async (pred: (a: any) => boolean) => {
  const s = useStore.getState().snap
  const a = s?.approvals.find((x) => x.status === 'pending' && pred(x))
  if (a) await api.post(`/api/approvals/${a.id}/approve`)
}

const STEPS: Step[] = [
  { title: 'Intact city', say: 'One live world model, rendered on the laptop and as a hologram (/holo under the Pepper\'s Ghost pyramid). Every marker comes from backend state; the AI never draws anything.',
    acts: [{ label: 'Reset city', run: async () => { await api.post('/api/scenario/reset') } }] },
  { title: 'Trigger the earthquake', say: 'The hazard is pure config (hazards/earthquake.json). It blocks corridors, cuts Main St and knocks out the Westside substation.',
    acts: [{ label: 'Trigger earthquake', run: () => api.post('/api/scenario/trigger', { hazard: 'earthquake' }) }] },
  { title: 'Distress reports arrive', say: 'Phones, a wearable fall beacon and traffic cams stream in. The Report Agent resolves "room 305" to an exact node and dedupes four lobby reports into one incident.' },
  { title: 'Agents triage', say: 'The Situation Agent ranks by severity, isolation, vulnerability and confidence, NOT report volume. Dr. Voss (alone, one low-confidence beacon) ranks #1; the busy lobby ranks last. Unknown-mobility people are held for assessment.' },
  { title: 'Independent people get routes', say: 'The Comms Agent calls route() for each evacuee: blocked edges excluded, unknown edges avoided, step-free paths for wheelchair users, and Central Ave kept clear for responders.',
    acts: [{ label: 'Focus Meridian Tower', run: () => setView({ focus_building: 'B1', focus_floor: null }) }] },
  { title: 'Rescue queue → approve', say: 'The Resource Agent proposes responder dispatches with access routes (magenta). Nothing moves until a human approves.',
    acts: [{ label: 'Approve top dispatch', run: () => approveFirst((a) => a.action === 'dispatch_responder') }] },
  { title: 'Civilian: "Stairwell 1 blocked"', say: 'From a phone on the same Wi-Fi (or here), a civilian reports the stairwell. The Report Agent marks it REPORTED blocked (amber dashed), unverified.',
    acts: [{ label: 'Send report as a phone', run: async () => { setView({ focus_building: 'B1', focus_floor: 2 }); await submitReport({ text: 'Stairwell 1 blocked by debris', node_id: 'B1-F2-S1', kind: 'blocked_route', device: 'demo-phone' }) } }] },
  { title: 'Routes recalculate', say: 'The Comms Agent re-routes everyone whose path used that flight over to Stairwell 2, in both views, and messages them. Promoting it to VERIFIED is an approval.',
    acts: [{ label: 'Approve verification', run: () => approveFirst((a) => a.action === 'verify_blocked') }] },
  { title: 'Simulation: next 24 hours', say: 'cascade_forecast propagates the failure over the dependency graph and hazard rules: aftershock decay, a weakened tower, gas-main fire spread, the hospital generator running dry. Violet = predicted, not confirmed.',
    acts: [{ label: '+6h', run: () => setView({ horizon: 6, focus_building: null, focus_floor: null }) }, { label: '+24h', run: () => setView({ horizon: 24 }) },
      { label: 'Approve gas shut-off', run: () => approveFirst((a) => a.action === 'shut_gas_valve') }] },
  { title: 'Lose the internet', say: 'Agents drop to local deterministic mode, messages queue, and phones relay reports peer-to-peer (Device B). On reconnect everything syncs.',
    acts: [{ label: 'Go offline', run: () => api.post('/api/offline', { offline: true }) },
      { label: 'Queue a report', run: () => submitReport({ text: 'Smoke coming from the floor below', node_id: 'B1-F3-C2', kind: 'hazard', device: 'demo-phone' }) },
      { label: 'Reconnect', run: () => api.post('/api/offline', { offline: false }) }] },
  { title: 'Bonus: cyberattack', say: 'Same five agents, different config. The attack spreads along dependencies and shared vendors, not geography. Backup hours decide when things fail.',
    acts: [{ label: 'Trigger cyberattack', run: async () => { await api.post('/api/scenario/trigger', { hazard: 'cyberattack' }); setTimeout(() => setView({ horizon: 24 }), 9000) } }] },
]

export default function Demo() {
  const [open, setOpen] = useState(false)
  const [i, setI] = useState(0)
  const [busy, setBusy] = useState(false)
  const step = STEPS[i]
  const run = async (a: Act) => { setBusy(true); try { await a.run() } finally { setBusy(false) } }
  return (
    <>
      <button className="btn btn-lime" onClick={() => setOpen((o) => !o)}>◈ Demo</button>
      {open && (
        <div className="panel slidein fixed top-[68px] left-[366px] z-40 w-[340px] p-3">
          <div className="flex items-center justify-between">
            <span className="panel-title !text-lime">Demo · step {i + 1}/{STEPS.length}</span>
            <button className="font-mono text-xs text-dim hover:text-white" onClick={() => setOpen(false)}>✕</button>
          </div>
          <div className="mt-1 flex gap-0.5">{STEPS.map((_, k) => <span key={k} className={`h-1 flex-1 ${k <= i ? 'bg-lime shadow-[0_0_6px_#00ffa3]' : 'bg-white/10'}`} />)}</div>
          <div className="mt-2 font-display text-sm tracking-wider text-white">{step.title}</div>
          <div className="mt-1 text-[12px] leading-snug text-white/75">{step.say}</div>
          {step.acts && <div className="mt-2 flex flex-wrap gap-1.5">{step.acts.map((a) => <button key={a.label} className="btn btn-magenta !py-1" disabled={busy} onClick={() => run(a)}>▶ {a.label}</button>)}</div>}
          <div className="mt-3 flex justify-between">
            <button className="btn !py-1" disabled={i === 0} onClick={() => setI(i - 1)}>◂ Back</button>
            <button className="btn btn-lime !py-1" disabled={i === STEPS.length - 1} onClick={() => setI(i + 1)}>Next ▸</button>
          </div>
        </div>
      )}
    </>
  )
}

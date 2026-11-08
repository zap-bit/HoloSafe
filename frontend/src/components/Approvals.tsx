import { useState } from 'react'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import { AGENT_COLOR } from '../lib/util'

const ICON: Record<string, string> = { dispatch_responder: '✚', verify_blocked: '⛔', declare_safe: '◎', shut_gas_valve: '⛽', fuel_resupply: '⚡', isolate_network: '⌁', restrict_entry: '⚠' }

export default function Approvals() {
  const snap = useStore((s) => s.snap)
  const [busy, setBusy] = useState<string | null>(null)
  if (!snap) return null
  const pending = snap.approvals.filter((a) => a.status === 'pending')
  const done = snap.approvals.filter((a) => a.status !== 'pending').slice(0, 4)
  const decide = async (id: string, d: 'approve' | 'reject') => {
    setBusy(id)
    try { await api.post(`/api/approvals/${id}/${d}`) } finally { setBusy(null) }
  }
  return (
    <div className="panel flex max-h-[46%] shrink-0 flex-col p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="panel-title">Human approval queue</span>
        <span className={`chip ${pending.length ? 'pulse-red text-amber' : 'text-dim'}`}>{pending.length} pending</span>
      </div>
      <div className="scroll-thin min-h-0 space-y-1.5 overflow-y-auto pr-1">
        {!pending.length && <div className="py-3 text-center font-mono text-[11px] text-dim">High-impact actions wait here for a human.</div>}
        {pending.map((a) => (
          <div key={a.id} className="slidein border border-amber/30 bg-amber/[0.04] p-2">
            <div className="flex items-start gap-2">
              <span className="text-lg leading-none text-amber">{ICON[a.action] ?? '◆'}</span>
              <div className="min-w-0 flex-1">
                <div className="text-[12px] leading-snug font-semibold text-white">{a.title}</div>
                <div className="mt-0.5 text-[11px] leading-snug text-white/60">{a.rationale}</div>
                <div className="mt-0.5 font-mono text-[10px]" style={{ color: AGENT_COLOR[a.proposed_by_agent] }}>proposed by {a.proposed_by_agent} · {a.action}</div>
              </div>
            </div>
            <div className="mt-1.5 flex justify-end gap-2">
              <button className="btn !py-1 !text-[9px]" disabled={busy === a.id} onClick={() => decide(a.id, 'reject')}>Reject</button>
              <button className="btn btn-lime !py-1 !text-[9px]" disabled={busy === a.id} onClick={() => decide(a.id, 'approve')}>Approve</button>
            </div>
          </div>
        ))}
        {done.map((a) => (
          <div key={a.id} className="flex items-center gap-2 px-1 font-mono text-[10px] text-dim">
            <span style={{ color: a.status === 'approved' ? '#3dff8f' : '#ff2a4d' }}>{a.status === 'approved' ? '✓' : '✗'}</span>
            <span className="truncate">{a.title}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

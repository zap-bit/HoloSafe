import { useStore } from '../lib/store'
import { setView } from './ScenePane'
import { PREDICTED } from '../lib/colors'

const STEPS = [0, 1, 6, 24]
const KIND_ICON: Record<string, string> = { aftershock: '≋', weakened_building: '▥', fire: '🜂', power_loss: '⚡', comms_loss: '📶', water_loss: '💧', traffic_loss: '🚦', compromise: '⌁' }

export function TimeSlider() {
  const snap = useStore((s) => s.snap)
  if (!snap?.scenario) return null
  const H = snap.view.horizon
  const counts = STEPS.map((h) => snap.forecasts.filter((f) => h > 0 && f.horizon_hours <= h && f.status === 'predicted').length)
  const idx = Math.max(0, STEPS.indexOf(H))
  return (
    <div className="panel pointer-events-auto absolute bottom-3 left-1/2 w-[440px] -translate-x-1/2 px-4 py-2">
      <div className="flex items-center justify-between">
        <span className="panel-title !text-violet [text-shadow:0_0_8px_#b366ff]">Forecast horizon</span>
        <span className="font-mono text-[10px] text-dim">predicted ≠ confirmed · violet volumes</span>
      </div>
      <div className="relative mt-2 h-8">
        <div className="absolute top-3 right-3 left-3 h-px bg-violet/40" />
        <div className="absolute top-[11px] left-3 h-[3px] bg-violet shadow-[0_0_10px_#b366ff] transition-all" style={{ width: `calc(${(idx / 3) * 100}% - ${(idx / 3) * 24}px)` }} />
        <div className="absolute inset-x-0 top-0 flex justify-between">
          {STEPS.map((h, i) => (
            <button key={h} onClick={() => setView({ horizon: h })} className="flex flex-col items-center gap-0.5">
              <span className={`h-6 w-6 rotate-45 border-2 transition ${i <= idx ? 'border-violet bg-violet/40 shadow-[0_0_12px_#b366ff]' : 'border-white/25 bg-black'}`} />
            </button>
          ))}
        </div>
      </div>
      <div className="flex justify-between font-display text-[10px] tracking-widest">
        {STEPS.map((h, i) => (
          <button key={h} onClick={() => setView({ horizon: h })} className={`w-12 text-center ${h === H ? 'text-white' : 'text-dim'}`}>
            {h === 0 ? 'NOW' : `+${h}H`}<div className="font-mono text-[9px] text-violet/80">{h ? `${counts[i]} fx` : 'confirmed'}</div>
          </button>
        ))}
      </div>
    </div>
  )
}

export function ForecastPanel() {
  const snap = useStore((s) => s.snap)
  if (!snap?.scenario || !snap.view.horizon) return null
  const H = snap.view.horizon
  const latest = new Map<string, (typeof snap.forecasts)[number]>()
  for (const f of snap.forecasts.filter((f) => f.horizon_hours <= H)) {
    const k = f.kind === 'aftershock' ? 'aftershock' : f.kind + f.target_id
    if (!latest.has(k) || latest.get(k)!.horizon_hours < f.horizon_hours) latest.set(k, f)
  }
  const list = [...latest.values()].sort((a, b) => (a.status === 'averted' ? 1 : 0) - (b.status === 'averted' ? 1 : 0) || a.horizon_hours - b.horizon_hours || b.confidence - a.confidence)
  // group fire spread into one line
  const fire = list.filter((f) => f.kind === 'fire')
  const shown = [...list.filter((f) => f.kind !== 'fire'), ...(fire.length ? [fire.sort((a, b) => b.confidence - a.confidence)[0]] : [])]
  return (
    <div className="panel pointer-events-auto absolute bottom-[104px] left-3 w-[350px] p-3">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="panel-title !text-violet [text-shadow:0_0_8px_#b366ff]">Simulation · next {H}h</span>
        <span className="font-mono text-[10px] text-dim">{list.length} effects · cascade_forecast</span>
      </div>
      <div className="scroll-thin max-h-[30vh] space-y-1.5 overflow-y-auto pr-1">
        {shown.map((f) => {
          const averted = f.status === 'averted'
          return (
            <div key={f.id} className={`slidein border-l-2 pl-2 ${averted ? 'opacity-50' : ''}`} style={{ borderColor: averted ? '#3dff8f' : f.kind === 'fire' ? '#ff6a3d' : PREDICTED }}>
              <div className="flex items-center gap-2 text-[11px]">
                <span>{KIND_ICON[f.kind] ?? '◆'}</span>
                <span className="font-display tracking-wider text-white uppercase">{f.kind.replace('_', ' ')}{f.kind === 'fire' && fire.length > 1 ? ` ×${fire.length} blocks` : ''}</span>
                <span className="chip !text-[9px] text-violet">+{f.horizon_hours}h</span>
                <span className="font-mono text-[10px] text-dim">conf {Math.round(f.confidence * 100)}%</span>
                {averted && <span className="chip !text-[9px] text-[#3dff8f]">AVERTED</span>}
              </div>
              <div className="text-[11px] leading-snug text-white/75">{f.explanation || f.reason}</div>
              {f.precaution && !averted && <div className="text-[11px] leading-snug text-amber">↳ {f.precaution} <span className="font-mono text-[10px] text-dim">by T+{f.deadline_hours}h</span></div>}
            </div>
          )
        })}
      </div>
    </div>
  )
}

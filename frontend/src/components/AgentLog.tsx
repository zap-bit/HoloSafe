import { useStore } from '../lib/store'
import { AGENT_COLOR } from '../lib/util'

export default function AgentLog() {
  const snap = useStore((s) => s.snap)
  if (!snap) return null
  return (
    <div className="panel flex min-h-0 flex-1 flex-col p-3">
      <div className="mb-2 flex items-center justify-between">
        <span className="panel-title">Agent activity</span>
        <span className="font-mono text-[10px] text-dim">live · tool calls streamed</span>
      </div>
      <div className="scroll-thin min-h-0 flex-1 space-y-2 overflow-y-auto pr-1">
        {!snap.agent_log.length && <div className="py-6 text-center font-mono text-xs text-dim">AGENTS IDLE — trigger a scenario</div>}
        {snap.agent_log.map((l) => {
          const c = AGENT_COLOR[l.agent] ?? '#cfe9f5'
          return (
            <div key={l.id} className="slidein border-l pl-2" style={{ borderColor: c + '88' }}>
              <div className="flex items-center gap-2">
                <span className="font-display text-[10px] tracking-[0.2em] uppercase" style={{ color: c, textShadow: `0 0 8px ${c}` }}>{l.agent}</span>
                {l.mode !== 'system' && <span className="chip !text-[9px]" style={{ color: l.mode === 'live' ? '#00ffa3' : '#ffb020' }}>{l.mode === 'live' ? 'NEMOTRON' : 'MOCK'}</span>}
                <span className="ml-auto font-mono text-[9px] text-dim">{new Date(l.ts).toLocaleTimeString()}</span>
              </div>
              <div className="truncate font-mono text-[10px] text-white/45">▸ {l.input_summary}</div>
              {l.tool_calls.length > 0 && (
                <div className="my-0.5 space-y-px">
                  {l.tool_calls.slice(0, 8).map((t, k) => (
                    <div key={k} className="truncate font-mono text-[10px] leading-tight">
                      <span style={{ color: c }}>ƒ {t.tool}</span><span className="text-white/35">({Object.keys(t.args).slice(0, 3).map((a) => `${a}=${String(t.args[a]).slice(0, 18)}`).join(', ')})</span>{' '}
                      <span className={t.result_summary.startsWith('✗') || t.result_summary.startsWith('⚠') ? 'text-red' : 'text-lime/70'}>{t.result_summary}</span>
                    </div>
                  ))}
                  {l.tool_calls.length > 8 && <div className="font-mono text-[10px] text-dim">… +{l.tool_calls.length - 8} more tool calls</div>}
                </div>
              )}
              <div className="text-[11.5px] leading-snug text-white/85">{l.output_summary}</div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

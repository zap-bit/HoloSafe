import { useStore } from '../lib/store'
import Logo from './Logo'

export default function Header({ children }: { children?: React.ReactNode }) {
  const link = useStore((s) => s.link)
  const fromCache = useStore((s) => s.fromCache)
  const snap = useStore((s) => s.snap)
  const offline = snap?.offline
  const mode = snap?.agent_mode
  const netColor = link !== 'live' ? '#ff2a4d' : offline ? '#ffb020' : '#00ffa3'
  const netLabel = link !== 'live' ? (fromCache ? 'LINK LOST · CACHED' : 'CONNECTING') : offline ? 'OFFLINE · MESH' : 'ONLINE'
  return (
    <header className="relative z-20 flex h-14 shrink-0 items-center gap-4 border-b border-cyan/20 bg-gradient-to-r from-[#061420] via-[#04060b] to-[#12061a] px-4">
      <Logo className="h-10 w-10 drop-shadow-[0_0_10px_#ff8a1f]" />
      <div className="leading-none">
        <div className="flicker font-display text-xl font-black tracking-[0.35em] text-white [text-shadow:0_0_12px_#19e6ff]">HOLOSAFE</div>
        <div className="mt-1 font-mono text-[10px] tracking-[0.3em] text-cyan/70">SEE · UNDERSTAND · EVACUATE · COORDINATE</div>
      </div>
      <div className="ml-4 flex items-center gap-2 font-mono text-[11px]">
        <span className="chip" style={{ color: netColor }}><span className="mr-1 inline-block h-1.5 w-1.5 animate-pulse rounded-full" style={{ background: netColor }} />{netLabel}</span>
        {mode && (
          <span className="chip" style={{ color: mode.mode === 'mock' ? '#ffb020' : '#00ffa3' }} title={mode.reason}>
            {mode.mode === 'mock' ? `MOCK · ${mode.reason}` : 'NEMOTRON LIVE'}
          </span>
        )}
        {snap?.scenario && <span className="chip pulse-red text-red">⚠ {snap.scenario.name}</span>}
        {snap?.busy && <span className="chip animate-pulse text-violet">AGENTS WORKING…</span>}
      </div>
      <div className="ml-auto flex items-center gap-2">{children}</div>
    </header>
  )
}

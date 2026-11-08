import { useEffect, useState } from 'react'
import Logo from './Logo'

/** Opening splash: logo (frontend/public/logo.*) glitches in, then the Command Center fades up. Click to skip. */
export default function Splash() {
  const [phase, setPhase] = useState<'in' | 'out' | 'gone'>('in')
  useEffect(() => {
    const a = setTimeout(() => setPhase('out'), 2600)
    const b = setTimeout(() => setPhase('gone'), 3300)
    return () => { clearTimeout(a); clearTimeout(b) }
  }, [])
  if (phase === 'gone') return null
  return (
    <div onClick={() => setPhase('gone')}
      className={`fixed inset-0 z-[100] grid cursor-pointer place-items-center bg-[radial-gradient(ellipse_at_center,#12061a_0%,#04060b_60%,#000_100%)] transition-opacity duration-700 ${phase === 'out' ? 'opacity-0' : 'opacity-100'}`}>
      <div className="flex flex-col items-center gap-5">
        <div className="relative">
          <div className="absolute -inset-10 animate-pulse rounded-full bg-[#ff8a1f]/10 blur-3xl" />
          <Logo className="glitch relative h-56 w-56 object-contain drop-shadow-[0_0_30px_#ff8a1f]" />
        </div>
        <div className="glitch font-display text-5xl font-black tracking-[0.5em] text-white [text-shadow:0_0_20px_#19e6ff,0_0_2px_#fff]">HOLOSAFE</div>
        <div className="font-mono text-xs tracking-[0.45em] text-cyan/80">SEE · UNDERSTAND · EVACUATE · COORDINATE</div>
        <div className="mt-2 flex gap-1">
          {Array.from({ length: 18 }, (_, i) => (
            <span key={i} className="h-1 w-4 bg-cyan/70 shadow-[0_0_8px_#19e6ff]" style={{ animation: `flicker 1.2s ${i * 0.07}s infinite` }} />
          ))}
        </div>
        <div className="font-mono text-[10px] tracking-[0.3em] text-dim">INITIALISING COMMAND MESH · NEMOTRON AGENTS · HOLO LINK</div>
      </div>
    </div>
  )
}

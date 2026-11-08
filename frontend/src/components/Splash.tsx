import { useEffect, useState } from 'react'

/**
 * Opening animation — implemented from the "0 · Opening animation" design export.
 * The 1100x900 artboard is reproduced 1:1 and scaled to fit the viewport.
 * Plays for ~4.6s, then fades into the Command Center. Click (or any key) to skip.
 */
const W = 1100
const H = 900
const HOLD_MS = 4600
const FADE_MS = 800

const CSS = `
.intro-z{font-family:'Zen Dots',sans-serif}.intro-m{font-family:'Share Tech Mono',monospace}
@keyframes intro-spin{to{transform:rotate(360deg)}}
@keyframes intro-spinr{to{transform:rotate(-360deg)}}
@keyframes intro-bob{50%{transform:translateY(-14px) rotate(1.5deg)}}
@keyframes intro-flick{0%,100%{filter:brightness(1) hue-rotate(0) drop-shadow(0 0 18px #ff6a1f)}30%{filter:brightness(1.35) hue-rotate(-12deg) drop-shadow(0 0 34px #ff9a2f)}60%{filter:brightness(.9) hue-rotate(8deg) drop-shadow(0 0 22px #ff3a1f)}}
@keyframes intro-ghost{0%,100%{opacity:.5;transform:scale(1.04)}50%{opacity:.9;transform:scale(1.1) translateY(-10px)}}
@keyframes intro-ember{0%{transform:translate(0,0) scale(1);opacity:0}15%{opacity:1}100%{transform:translate(var(--dx),-340px) scale(.2);opacity:0}}
@keyframes intro-sweep{0%{top:90px;opacity:0}10%,90%{opacity:.9}100%{top:760px;opacity:0}}
@keyframes intro-tick{50%{opacity:.3}}
@keyframes intro-load{from{width:0}to{width:100%}}
.intro-e{position:absolute;width:6px;height:6px;border-radius:50%;background:#ffb347;box-shadow:0 0 10px #ff6a1f;animation:intro-ember 3.2s linear infinite}
`

const EMBERS: { left: number; top: number; dx: number; delay: number }[] = [
  { left: 480, top: 520, dx: -40, delay: 0 },
  { left: 540, top: 560, dx: 30, delay: 0.6 },
  { left: 600, top: 500, dx: 60, delay: 1.1 },
  { left: 440, top: 600, dx: -70, delay: 1.7 },
  { left: 580, top: 610, dx: -20, delay: 2.2 },
  { left: 650, top: 560, dx: 40, delay: 2.7 },
]

function useFitScale() {
  const calc = () => Math.min(window.innerWidth / W, window.innerHeight / H)
  const [scale, setScale] = useState(calc)
  useEffect(() => {
    const on = () => setScale(calc())
    window.addEventListener('resize', on)
    return () => window.removeEventListener('resize', on)
  }, [])
  return scale
}

export default function Splash() {
  const [phase, setPhase] = useState<'in' | 'out' | 'gone'>('in')
  const scale = useFitScale()

  useEffect(() => {
    const a = setTimeout(() => setPhase('out'), HOLD_MS)
    const b = setTimeout(() => setPhase('gone'), HOLD_MS + FADE_MS)
    const skip = () => setPhase('gone')
    window.addEventListener('keydown', skip)
    return () => { clearTimeout(a); clearTimeout(b); window.removeEventListener('keydown', skip) }
  }, [])

  if (phase === 'gone') return null
  return (
    <div
      onClick={() => setPhase('gone')}
      className="fixed inset-0 z-[100] grid cursor-pointer place-items-center overflow-hidden"
      style={{ background: '#02030a', opacity: phase === 'out' ? 0 : 1, transition: `opacity ${FADE_MS}ms ease` }}
    >
      <style>{CSS}</style>
      <div style={{ width: W * scale, height: H * scale, position: 'relative' }}>
        <div style={{ position: 'absolute', left: 0, top: 0, width: W, height: H, overflow: 'hidden', background: '#02030a', transform: `scale(${scale})`, transformOrigin: '0 0' }}>
          <img src="/intro/backdrop.png" alt="" style={{ position: 'absolute', left: '50%', top: 0, height: '100%', transform: 'translateX(-50%)', opacity: 0.14, mixBlendMode: 'screen' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(circle at 50% 52%,rgba(25,230,255,.14),transparent 55%)' }} />
          <svg style={{ position: 'absolute', inset: 0 }} width={W} height={H} viewBox={`0 0 ${W} ${H}`}>
            <ellipse cx="550" cy="790" rx="360" ry="90" fill="none" stroke="#19e6ff" strokeOpacity=".5" />
            <ellipse cx="550" cy="790" rx="250" ry="62" fill="none" stroke="#ff2bd6" strokeOpacity=".5" strokeDasharray="4 10" />
            <g style={{ transformOrigin: '550px 440px', animation: 'intro-spin 40s linear infinite' }}>
              <circle cx="550" cy="440" r="330" fill="none" stroke="#19e6ff" strokeOpacity=".35" strokeDasharray="2 14" />
            </g>
            <g style={{ transformOrigin: '550px 440px', animation: 'intro-spinr 28s linear infinite' }}>
              <circle cx="550" cy="440" r="290" fill="none" stroke="#7a3cff" strokeOpacity=".6" strokeDasharray="60 30 6 30" />
            </g>
            <path d="M550 790 L550 130" stroke="#19e6ff" strokeOpacity=".25" />
            <g stroke="#19e6ff" strokeOpacity=".5">
              <path d="M180 90v-30h30M920 90v-30h-30M180 810v30h30M920 810v30h-30" fill="none" />
            </g>
          </svg>
          <img src="/intro/phoenix.png" alt="" style={{ position: 'absolute', left: 300, top: 40, width: 500, opacity: 0.7, mixBlendMode: 'screen', filter: 'blur(16px) hue-rotate(160deg)', animation: 'intro-ghost 3s ease-in-out infinite' }} />
          <img src="/intro/phoenix.png" alt="Phoenix drone" style={{ position: 'absolute', left: 300, top: 40, width: 500, animation: 'intro-bob 5s ease-in-out infinite, intro-flick 1.8s steps(8) infinite' }} />
          {EMBERS.map((e, i) => (
            <span key={i} className="intro-e" style={{ left: e.left, top: e.top, ['--dx' as string]: `${e.dx}px`, animationDelay: `${e.delay}s` }} />
          ))}
          <div style={{ position: 'absolute', left: 230, right: 230, height: 2, background: '#19e6ff', boxShadow: '0 0 24px #19e6ff', animation: 'intro-sweep 5s linear infinite' }} />
          <div className="intro-z" style={{ position: 'absolute', left: 0, right: 0, top: 700, textAlign: 'center', fontSize: 84, letterSpacing: 14, color: '#fff', fontStyle: 'italic', textShadow: '5px 0 #ff2bd6,-5px 0 #19e6ff' }}>HOLO</div>
          <div className="intro-m" style={{ position: 'absolute', left: 0, right: 0, top: 810, textAlign: 'center', fontSize: 14, letterSpacing: 8, color: '#19e6ff' }}>
            SPATIAL EMERGENCY COORDINATION · INITIALIZING<span style={{ animation: 'intro-tick 1s infinite' }}> ▌</span>
          </div>
          {/* Purple loading bar — fills over the splash hold time */}
          <div style={{ position: 'absolute', left: 330, right: 330, top: 600, height: 6, border: '1px solid rgba(122,60,255,.55)', background: 'rgba(122,60,255,.12)', boxShadow: '0 0 12px rgba(122,60,255,.35)' }}>
            <div style={{ height: '100%', width: 0, background: 'linear-gradient(90deg,#7a3cff,#b46bff)', boxShadow: '0 0 14px #9b5cff, 0 0 4px #d9b8ff', animation: `intro-load ${HOLD_MS}ms linear forwards` }} />
          </div>
        </div>
      </div>
    </div>
  )
}

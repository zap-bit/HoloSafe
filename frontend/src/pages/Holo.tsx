import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import { CityScene } from '../scene/CityScene'
import { useStore } from '../lib/store'

/**
 * Pepper's Ghost display: the SAME scene rendered 4x in a cross (top/bottom/left/right),
 * each view's "up" pointing away from the screen centre so the pyramid faces show it upright.
 * One WebGL context, four scissored viewports, four cameras at 90° azimuth steps.
 */

interface Cal { size: number; gap: number; ox: number; oy: number; dist: number; rotate: boolean; mirror: boolean; guide: boolean }
const DEFAULT: Cal = { size: 0, gap: 12, ox: 0, oy: 0, dist: 180, rotate: true, mirror: false, guide: false }
const KEY = 'holosafe:holo-cal-v2'
const TARGET = new THREE.Vector3(10, 4, -5)

const autoSize = () => Math.round(Math.min(innerWidth, innerHeight) / 3.1)

function loadCal(): Cal {
  try { return { ...DEFAULT, ...JSON.parse(localStorage.getItem(KEY) || '{}') } } catch { return DEFAULT }
}

function QuadRender({ cal }: { cal: Cal }) {
  const { gl, scene, size } = useThree()
  const cams = useMemo(() => [0, 1, 2, 3].map(() => new THREE.PerspectiveCamera(34, 1, 1, 2000)), [])
  const flip = useMemo(() => new THREE.Matrix4().makeScale(-1, 1, 1), [])
  const theta = useRef(0)
  const target = useRef(TARGET.clone())
  const zoom = useRef(1)

  useFrame((_, dt) => {
    if (cal.rotate) theta.current += dt * 0.12
    // follow the Command Center's building focus (shared via backend view state)
    const snap = useStore.getState().snap
    const fb = snap?.buildings.find((b) => b.id === snap.view.focus_building)
    const want = fb ? new THREE.Vector3(fb.position.x, fb.footprint.h / 2, fb.position.z) : TARGET
    target.current.lerp(want, Math.min(1, dt * 2.5))
    zoom.current += ((fb ? 0.42 : 1) - zoom.current) * Math.min(1, dt * 2.5)
    const W = size.width, H = size.height
    const S = cal.size || Math.round(Math.min(W, H) / 3.1)
    const g = S / 2 + cal.gap // inner edge distance from centre; never overlaps
    const T = target.current, dist = cal.dist * zoom.current
    const cx = W / 2 + cal.ox, cy = H / 2 + cal.oy
    // [cssX, cssY, azimuth, roll]: roll makes each image's top point outward
    const panels: [number, number, number, number][] = [
      [cx - S / 2, cy - g - S, 0, 0],                  // top
      [cx - S / 2, cy + g, Math.PI, Math.PI],          // bottom
      [cx - g - S, cy - S / 2, Math.PI / 2, -Math.PI / 2], // left
      [cx + g, cy - S / 2, -Math.PI / 2, Math.PI / 2],  // right
    ]
    gl.autoClear = false
    gl.setScissorTest(false)
    gl.setClearColor('#000000', 1)
    gl.clear()
    gl.setScissorTest(true)
    const el = 0.42
    panels.forEach(([x, y, az0, roll], i) => {
      const cam = cams[i]
      const az = az0 + theta.current
      cam.position.set(
        T.x + Math.sin(az) * dist * Math.cos(el),
        T.y + dist * Math.sin(el),
        T.z + Math.cos(az) * dist * Math.cos(el),
      )
      cam.up.set(0, 1, 0)
      cam.lookAt(T)
      cam.rotateZ(roll)
      cam.aspect = 1
      cam.updateProjectionMatrix()
      if (cal.mirror) cam.projectionMatrix.multiply(flip)
      const glY = H - y - S
      gl.setViewport(x, glY, S, S)
      gl.setScissor(x, glY, S, S)
      gl.render(scene, cam)
    })
    gl.setScissorTest(false)
  }, 1)
  return null
}

export default function Holo() {
  const [cal, setCal] = useState<Cal>(loadCal)
  const [hint, setHint] = useState<string | null>(null)
  const [help, setHelp] = useState(false)
  const snap = useStore((s) => s.snap)
  const timer = useRef<number>(0)

  useEffect(() => {
    try { localStorage.setItem(KEY, JSON.stringify(cal)) } catch { /* private mode */ }
  }, [cal])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const big = e.shiftKey ? 5 : 1
      const upd: Partial<Cal> | null = (() => {
        switch (e.key) {
          case '=': case '+': return { size: (cal.size || autoSize()) + 10 * big }
          case '-': case '_': return { size: Math.max(60, (cal.size || autoSize()) - 10 * big) }
          case ']': return { gap: cal.gap + 4 * big }
          case '[': return { gap: Math.max(0, cal.gap - 4 * big) }
          case 'ArrowUp': return { oy: cal.oy - 4 * big }
          case 'ArrowDown': return { oy: cal.oy + 4 * big }
          case 'ArrowLeft': return { ox: cal.ox - 4 * big }
          case 'ArrowRight': return { ox: cal.ox + 4 * big }
          case ',': return { dist: cal.dist + 6 * big }
          case '.': return { dist: Math.max(40, cal.dist - 6 * big) }
          case 'r': return { rotate: !cal.rotate }
          case 'm': return { mirror: !cal.mirror }
          case 'g': return { guide: !cal.guide }
          case '0': return { ...DEFAULT }
          case 'f': document.documentElement.requestFullscreen?.().catch(() => {}); return null
          case 'h': case '?': setHelp((h) => !h); return null
          default: return null
        }
      })()
      if (!upd) return
      e.preventDefault()
      const next = { ...cal, ...upd }
      setCal(next)
      setHint(`size ${next.size || 'auto'}px · gap ${next.gap}px · offset ${next.ox},${next.oy} · zoom ${next.dist} · rotate ${next.rotate ? 'on' : 'off'} · mirror ${next.mirror ? 'on' : 'off'}`)
      clearTimeout(timer.current)
      timer.current = window.setTimeout(() => setHint(null), 1600)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [cal])

  return (
    <div className="fixed inset-0 cursor-none bg-black">
      <Canvas dpr={[1, 2]} gl={{ antialias: true }} style={{ background: '#000' }}>
        <CityScene holo />
        <QuadRender cal={cal} />
      </Canvas>
      {cal.guide && (
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute top-0 bottom-0 w-px bg-cyan/40" style={{ left: `calc(50% + ${cal.ox}px)` }} />
          <div className="absolute right-0 left-0 h-px bg-cyan/40" style={{ top: `calc(50% + ${cal.oy}px)` }} />
          <div className="absolute border border-cyan/60" style={{ width: (cal.size || autoSize()) + cal.gap * 2, height: (cal.size || autoSize()) + cal.gap * 2, left: `calc(50% + ${cal.ox - (cal.size || autoSize()) / 2 - cal.gap}px)`, top: `calc(50% + ${cal.oy - (cal.size || autoSize()) / 2 - cal.gap}px)` }} />
        </div>
      )}
      {hint && <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 font-mono text-xs text-cyan/70">{hint}</div>}
      {help && (
        <div className="absolute top-4 left-4 border border-cyan/40 bg-black/80 p-4 font-mono text-xs leading-6 text-cyan/90">
          HOLO CALIBRATION<br />
          + / − ……… view size (shift = ×5)<br />
          [ / ] ……… gap from centre<br />
          arrows …… move centre<br />
          , / . ……… zoom out / in<br />
          r …………… auto-rotate on/off<br />
          m …………… mirror (if text/scene reads reversed)<br />
          g …………… centre guide<br />
          f …………… fullscreen · 0 reset · h help
        </div>
      )}
      {!snap && <div className="absolute inset-0 grid place-items-center font-mono text-xs text-cyan/40">AWAITING LINK…</div>}
    </div>
  )
}

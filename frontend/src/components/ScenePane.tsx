import { Canvas } from '@react-three/fiber'
import { OrbitControls } from '@react-three/drei'
import { EffectComposer, Bloom } from '@react-three/postprocessing'
import { CityScene } from '../scene/CityScene'
import { useStore } from '../lib/store'
import { api } from '../lib/api'
import { LabelOverlay, LabelProjector, sceneLabels } from '../scene/labels'
import { useMemo } from 'react'
import { ForecastPanel, TimeSlider } from './Forecasts'

export function setView(v: { horizon?: number; focus_building?: string | null; focus_floor?: number | null }) {
  api.post('/api/view', v).catch(() => {})
}

export default function ScenePane() {
  const snap = useStore((s) => s.snap)
  const labels = useMemo(() => sceneLabels(snap), [snap])
  return (
    <div className="absolute inset-0">
      <Canvas camera={{ position: [-20, 85, 105], fov: 42, near: 1, far: 2000 }} dpr={[1, 2]} gl={{ antialias: true }}
        onPointerMissed={() => {}}>
        <color attach="background" args={['#02050a']} />
        <fog attach="fog" args={['#02050a', 160, 330]} />
        <CityScene interactive onPickBuilding={(id) => setView({ focus_building: id, focus_floor: null })} />
        <LabelProjector labels={labels} />
        <OrbitControls makeDefault target={[10, 0, -5]} maxPolarAngle={Math.PI / 2.1} minDistance={25} maxDistance={260} enableDamping />
        <EffectComposer>
          <Bloom intensity={1.1} luminanceThreshold={0.15} luminanceSmoothing={0.3} mipmapBlur radius={0.7} />
        </EffectComposer>
      </Canvas>
      <LabelOverlay labels={labels} />
      <FocusBar />
      <ForecastPanel />
      <TimeSlider />
    </div>
  )
}

function FocusBar() {
  const snap = useStore((s) => s.snap)
  if (!snap) return null
  const { focus_building: fb, focus_floor: ff } = snap.view
  const b = snap.buildings.find((x) => x.id === fb)
  return (
    <div className="pointer-events-auto absolute top-3 left-1/2 flex -translate-x-1/2 items-center gap-2">
      {snap.buildings.map((x) => (
        <button key={x.id} className={`btn ${fb === x.id ? '!bg-cyan/25 !text-white' : ''}`}
          onClick={() => setView({ focus_building: fb === x.id ? null : x.id, focus_floor: null })}>
          {x.name}
        </button>
      ))}
      {b && (
        <div className="panel ml-2 flex items-center gap-1 px-2 py-1">
          <span className="panel-title mr-1">FLOOR</span>
          <button className="btn !px-2" disabled={ff === null} onClick={() => setView({ focus_floor: ff && ff > 1 ? ff - 1 : null })}>▼</button>
          <span className="w-10 text-center font-mono text-sm text-cyan">{ff ?? 'ALL'}</span>
          <button className="btn !px-2" disabled={ff === b.floors} onClick={() => setView({ focus_floor: ff ? ff + 1 : 1 })}>▲</button>
        </div>
      )}
    </div>
  )
}

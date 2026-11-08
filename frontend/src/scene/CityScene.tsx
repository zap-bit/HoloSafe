import { useMemo, useRef } from 'react'
import { useFrame } from '@react-three/fiber'
import { Line } from '@react-three/drei'
import * as THREE from 'three'
import { useStore } from '../lib/store'
import type { Building, Edge, Forecast, GNode, Snapshot } from '../lib/types'
import { CYAN, EDGE, PERSON, PREDICTED, ROUTE_CIVILIAN, ROUTE_RESPONDER, SEVERITY } from '../lib/colors'

/** Renders ONLY structured backend state. No AI-generated visuals (architecture rule 1). */

type V3 = [number, number, number]
const LIFT = 0.25

export interface SceneOpts {
  holo?: boolean            // brighter / thicker, no DOM labels (pyramid display)
  interactive?: boolean     // click buildings to isolate
  onPickBuilding?: (id: string | null) => void
}

function useFocus(snap: Snapshot) {
  const { focus_building: fb, focus_floor: ff } = snap.view
  /** 1 = full, 0.25 = context, 0.06 = ghost */
  const nodeAlpha = (n: GNode | undefined) => {
    if (!n) return 1
    if (!fb) return 1
    if (n.building_id !== fb) return n.building_id ? 0.06 : 0.35
    if (ff == null) return 1
    return n.floor === ff ? 1 : 0.12
  }
  return { fb, ff, nodeAlpha }
}

export function CityScene({ holo = false, interactive = false, onPickBuilding }: SceneOpts) {
  const snap = useStore((s) => s.snap)
  if (!snap || !snap.nodes.length) return null
  return <SceneInner snap={snap} holo={holo} interactive={interactive} onPickBuilding={onPickBuilding} />
}

function SceneInner({ snap, holo, interactive, onPickBuilding }: SceneOpts & { snap: Snapshot }) {
  const nodes = useMemo(() => new Map(snap.nodes.map((n) => [n.id, n])), [snap.nodes])
  const focus = useFocus(snap)
  return (
    <group>
      <Ground holo={!!holo} />
      {snap.buildings.map((b) => (
        <BuildingMesh key={b.id} b={b} snap={snap} holo={!!holo} interactive={!!interactive} onPick={onPickBuilding} />
      ))}
      <Edges snap={snap} nodes={nodes} holo={!!holo} focus={focus} />
      <SafeZones snap={snap} nodes={nodes} holo={!!holo} />
      <Routes snap={snap} nodes={nodes} holo={!!holo} focus={focus} />
      <People snap={snap} nodes={nodes} holo={!!holo} focus={focus} />
      <Incidents snap={snap} nodes={nodes} holo={!!holo} focus={focus} />
      <Responders snap={snap} nodes={nodes} holo={!!holo} />
      <InfraLayer snap={snap} nodes={nodes} holo={!!holo} />
      <Forecasts snap={snap} nodes={nodes} holo={!!holo} />
      <EdgePulses snap={snap} nodes={nodes} />
    </group>
  )
}

/* ---------------------------------------------------------------- ground */
function Ground({ holo }: { holo: boolean }) {
  return (
    <group position={[10, -0.05, -5]}>
      {!holo && (
        <mesh rotation-x={-Math.PI / 2}>
          <planeGeometry args={[200, 160]} />
          <meshBasicMaterial color="#03070d" transparent opacity={0.9} />
        </mesh>
      )}
      <gridHelper args={[200, 50, holo ? '#0f3a4a' : '#0b2a36', holo ? '#0a2430' : '#081a24']} position={[0, 0.01, 0]} />
    </group>
  )
}

/* ------------------------------------------------------------- buildings */
function BuildingMesh({ b, snap, holo, interactive, onPick }: { b: Building; snap: Snapshot; holo: boolean; interactive: boolean; onPick?: (id: string | null) => void }) {
  const { focus_building: fb, focus_floor: ff } = snap.view
  const isFocus = fb === b.id
  const ghost = fb && !isFocus
  const fh = b.footprint.h / b.floors
  const damaged = snap.edges.some((e) => e.status === 'verified_blocked' && e.a.startsWith(b.id + '-'))
  const weakened = snap.forecasts.some((f) => f.target_id === b.id && f.status === 'predicted' && f.horizon_hours <= snap.view.horizon && snap.view.horizon > 0)
  const base = damaged ? '#ff5577' : CYAN
  const edgeOpacity = ghost ? 0.08 : holo ? 0.95 : 0.7
  const boxGeo = useMemo(() => new THREE.BoxGeometry(b.footprint.w, b.footprint.h, b.footprint.d), [b])
  const edgesGeo = useMemo(() => new THREE.EdgesGeometry(boxGeo), [boxGeo])
  const slabGeo = useMemo(() => new THREE.EdgesGeometry(new THREE.BoxGeometry(b.footprint.w, 0.05, b.footprint.d)), [b])
  return (
    <group position={[b.position.x, 0, b.position.z]}>
      <mesh
        position={[0, b.footprint.h / 2, 0]}
        geometry={boxGeo}
        onClick={interactive ? (e) => { e.stopPropagation(); onPick?.(isFocus ? null : b.id) } : undefined}
        onPointerOver={interactive ? () => (document.body.style.cursor = 'pointer') : undefined}
        onPointerOut={interactive ? () => (document.body.style.cursor = '') : undefined}
      >
        <meshBasicMaterial color={base} transparent opacity={ghost ? 0.01 : isFocus ? 0.025 : holo ? 0.05 : 0.04} depthWrite={false} />
      </mesh>
      <lineSegments geometry={edgesGeo} position={[0, b.footprint.h / 2, 0]}>
        <lineBasicMaterial color={base} transparent opacity={edgeOpacity} toneMapped={false} />
      </lineSegments>
      {Array.from({ length: b.floors }, (_, i) => {
        const floor = i + 1
        const on = isFocus && ff === floor
        return (
          <group key={floor} position={[0, i * fh, 0]}>
            <lineSegments geometry={slabGeo}>
              <lineBasicMaterial color={on ? '#ffffff' : base} transparent opacity={ghost ? 0.05 : on ? 1 : isFocus && ff ? 0.15 : 0.35} toneMapped={false} />
            </lineSegments>
            <mesh rotation-x={-Math.PI / 2} position={[0, 0.02, 0]}>
              <planeGeometry args={[b.footprint.w, b.footprint.d]} />
              <meshBasicMaterial color={on ? '#19e6ff' : base} transparent opacity={ghost ? 0.005 : on ? 0.12 : 0.03} depthWrite={false} side={THREE.DoubleSide} />
            </mesh>
          </group>
        )
      })}
      {weakened && <WeakenedShell b={b} />}
    </group>
  )
}

function WeakenedShell({ b }: { b: Building }) {
  const ref = useRef<THREE.MeshBasicMaterial>(null)
  useFrame(({ clock }) => { if (ref.current) ref.current.opacity = 0.08 + 0.06 * Math.sin(clock.elapsedTime * 3) })
  return (
    <mesh position={[0, b.footprint.h / 2, 0]} scale={1.06}>
      <boxGeometry args={[b.footprint.w, b.footprint.h, b.footprint.d]} />
      <meshBasicMaterial ref={ref} color={PREDICTED} transparent opacity={0.1} depthWrite={false} wireframe />
    </mesh>
  )
}

/* ----------------------------------------------------------------- edges */
function Edges({ snap, nodes, holo, focus }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean; focus: ReturnType<typeof useFocus> }) {
  const buckets = useMemo(() => {
    const m = new Map<string, { status: string; alpha: number; street: boolean; pts: V3[] }>()
    for (const e of snap.edges) {
      const a = nodes.get(e.a), b = nodes.get(e.b)
      if (!a || !b) continue
      const alpha = Math.min(focus.nodeAlpha(a), focus.nodeAlpha(b))
      const street = a.kind === 'street' || b.kind === 'street' || a.kind === 'safe_zone' || b.kind === 'safe_zone'
      const tier = alpha > 0.5 ? 1 : alpha > 0.1 ? 0.3 : 0.07
      const key = `${e.status}|${tier}|${street}`
      if (!m.has(key)) m.set(key, { status: e.status, alpha: tier, street, pts: [] })
      m.get(key)!.pts.push([a.x, a.y + LIFT, a.z], [b.x, b.y + LIFT, b.z])
    }
    return [...m.values()]
  }, [snap.edges, nodes, focus.fb, focus.ff])
  return (
    <group>
      {buckets.map((bk) => {
        const blocked = bk.status === 'reported_blocked' || bk.status === 'verified_blocked'
        const w = (bk.street ? 2.2 : 1.2) * (holo ? 1.6 : 1) * (blocked ? 2 : 1)
        return (
          <Line
            key={`${bk.status}-${bk.alpha}-${bk.street}`}
            points={bk.pts}
            segments
            color={EDGE[bk.status]}
            lineWidth={w}
            transparent
            opacity={(bk.status === 'unknown' ? 0.55 : bk.street ? 0.55 : 0.4) * bk.alpha * (holo ? 1.5 : 1) + (blocked ? 0.4 : 0)}
            dashed={bk.status === 'reported_blocked'}
            dashSize={0.8}
            gapSize={0.6}
            toneMapped={false}
          />
        )
      })}
    </group>
  )
}

function EdgePulses({ snap, nodes }: { snap: Snapshot; nodes: Map<string, GNode> }) {
  // Diff edge statuses between snapshots → expanding ring where something changed.
  const prev = useRef<Map<string, string> | null>(null)
  const pulses = useRef<{ id: string; at: number; color: string; pos: V3 }[]>([])
  const now = performance.now()
  if (prev.current) {
    for (const e of snap.edges) {
      const p = prev.current.get(e.id)
      if (p && p !== e.status) {
        const a = nodes.get(e.a)!, b = nodes.get(e.b)!
        pulses.current.push({ id: e.id + now, at: now, color: EDGE[e.status], pos: [(a.x + b.x) / 2, (a.y + b.y) / 2 + LIFT, (a.z + b.z) / 2] })
      }
    }
  }
  prev.current = new Map(snap.edges.map((e) => [e.id, e.status]))
  pulses.current = pulses.current.filter((p) => now - p.at < 5000)
  return <>{pulses.current.map((p) => <PulseRing key={p.id} at={p.at} color={p.color} pos={p.pos} />)}</>
}

function PulseRing({ at, color, pos }: { at: number; color: string; pos: V3 }) {
  const ref = useRef<THREE.Mesh>(null)
  useFrame(() => {
    const t = ((performance.now() - at) % 1500) / 1500
    const life = (performance.now() - at) / 5000
    if (!ref.current) return
    ref.current.scale.setScalar(1 + t * 5)
    ;(ref.current.material as THREE.MeshBasicMaterial).opacity = Math.max(0, (1 - t) * (1 - life))
  })
  return (
    <mesh ref={ref} position={pos} rotation-x={-Math.PI / 2}>
      <ringGeometry args={[0.8, 1.1, 32]} />
      <meshBasicMaterial color={color} transparent toneMapped={false} side={THREE.DoubleSide} depthWrite={false} />
    </mesh>
  )
}

/* ------------------------------------------------------------ safe zones */
function SafeZones({ snap, nodes, holo }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean }) {
  return (
    <group>
      {snap.nodes.filter((n) => n.kind === 'safe_zone').map((n) => {
        const res = snap.resources.find((r) => r.node_id === n.id && r.kind === 'shelter')
        const verified = !snap.scenario || res?.status === 'verified'
        const color = verified ? '#3dff8f' : '#ffe14d'
        return (
          <group key={n.id} position={[n.x, 0.05, n.z]}>
            <mesh rotation-x={-Math.PI / 2}>
              <ringGeometry args={[5.2, 6, 48]} />
              <meshBasicMaterial color={color} transparent opacity={holo ? 0.95 : 0.8} toneMapped={false} side={THREE.DoubleSide} />
            </mesh>
            <mesh rotation-x={-Math.PI / 2}>
              <circleGeometry args={[5.2, 48]} />
              <meshBasicMaterial color={color} transparent opacity={0.08} side={THREE.DoubleSide} depthWrite={false} />
            </mesh>
            <mesh position={[0, 6, 0]}>
              <cylinderGeometry args={[0.15, 0.15, 12, 8]} />
              <meshBasicMaterial color={color} transparent opacity={0.6} toneMapped={false} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

/* ---------------------------------------------------------------- routes */
function Routes({ snap, nodes, holo, focus }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean; focus: ReturnType<typeof useFocus> }) {
  return (
    <group>
      {snap.routes.map((r) => {
        const pts = r.path.map((id) => nodes.get(id)).filter(Boolean) as GNode[]
        if (pts.length < 2) return null
        const alpha = Math.max(...pts.map((p) => focus.nodeAlpha(p)))
        return <RouteLine key={r.id} pts={pts} responder={r.subject_type === 'responder'} proposed={r.status === 'proposed'} holo={holo} alpha={alpha} />
      })}
    </group>
  )
}

function RouteLine({ pts, responder, proposed, holo, alpha }: { pts: GNode[]; responder: boolean; proposed: boolean; holo: boolean; alpha: number }) {
  const lineRef = useRef<any>(null)
  const dotRef = useRef<THREE.Mesh>(null)
  const born = useRef(performance.now())
  const lift = responder ? 0.9 : 0.55
  const points = useMemo(() => pts.map((p) => new THREE.Vector3(p.x, p.y + lift, p.z)), [pts, lift])
  const curve = useMemo(() => new THREE.CatmullRomCurve3(points, false, 'catmullrom', 0.05), [points])
  const color = responder ? ROUTE_RESPONDER : ROUTE_CIVILIAN
  useFrame((_, dt) => {
    const age = (performance.now() - born.current) / 900
    if (lineRef.current?.material) {
      const m = lineRef.current.material
      m.dashOffset -= dt * (responder ? 6 : 4)
      m.opacity = Math.min(1, age) * (proposed ? 0.55 : 0.95) * Math.max(alpha, 0.15)
    }
    if (dotRef.current) {
      const t = ((performance.now() / 1000) * (responder ? 0.22 : 0.15) + points[0].x * 0.01) % 1
      dotRef.current.position.copy(curve.getPointAt(Math.abs(t)))
    }
  })
  return (
    <group>
      <Line ref={lineRef} points={points} color={color} lineWidth={(holo ? 3.2 : 2.2) * (responder ? 1.3 : 1)} transparent opacity={0}
        dashed dashSize={proposed ? 0.7 : 2.2} gapSize={proposed ? 1.2 : 0.8} toneMapped={false} />
      <mesh ref={dotRef}>
        <sphereGeometry args={[responder ? 0.7 : 0.45, 12, 12]} />
        <meshBasicMaterial color={color} toneMapped={false} transparent opacity={Math.max(alpha, 0.2)} />
      </mesh>
    </group>
  )
}

/* ---------------------------------------------------------------- people */
function People({ snap, nodes, holo, focus }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean; focus: ReturnType<typeof useFocus> }) {
  // Spread people sharing a node so markers don't overlap.
  const seen = new Map<string, number>()
  return (
    <group>
      {snap.people.map((p) => {
        const n = nodes.get(p.node_id)
        if (!n) return null
        const k = seen.get(n.id) ?? 0
        seen.set(n.id, k + 1)
        const off: V3 = [Math.cos(k * 2.1) * 0.9 * Math.min(k, 1), 0, Math.sin(k * 2.1) * 0.9 * Math.min(k, 1)]
        const status = p.needs_assessment ? 'needs_assessment' : p.status
        return <PersonMarker key={p.id} pos={[n.x + off[0], n.y + 1.1, n.z + off[2]]} color={PERSON[status] ?? '#e8f6ff'}
          assist={p.mobility === 'needs_assist'} unknown={p.mobility === 'unknown'} alpha={focus.nodeAlpha(n)} holo={holo} alarm={status === 'trapped' || status === 'injured'} />
      })}
    </group>
  )
}

function PersonMarker({ pos, color, assist, unknown, alpha, holo, alarm }: { pos: V3; color: string; assist: boolean; unknown: boolean; alpha: number; holo: boolean; alarm: boolean }) {
  const ref = useRef<THREE.Group>(null)
  const seed = useMemo(() => Math.random() * 10, [])
  useFrame(({ clock }) => {
    if (!ref.current) return
    ref.current.position.y = pos[1] + Math.sin(clock.elapsedTime * 2 + seed) * 0.15
    if (alarm) ref.current.scale.setScalar(1 + 0.25 * Math.max(0, Math.sin(clock.elapsedTime * 6)))
  })
  const a = Math.max(alpha, 0.08)
  return (
    <group ref={ref} position={pos}>
      <mesh>
        <octahedronGeometry args={[holo ? 0.75 : 0.6, 0]} />
        <meshBasicMaterial color={color} toneMapped={false} transparent opacity={a} />
      </mesh>
      {(assist || unknown) && (
        <mesh rotation-x={-Math.PI / 2} position={[0, -0.8, 0]}>
          <ringGeometry args={[0.9, 1.15, 20]} />
          <meshBasicMaterial color={unknown ? '#ffe14d' : '#9fd8ff'} toneMapped={false} transparent opacity={a} side={THREE.DoubleSide} />
        </mesh>
      )}
    </group>
  )
}

/* ------------------------------------------------------------- incidents */
function Incidents({ snap, nodes, holo, focus }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean; focus: ReturnType<typeof useFocus> }) {
  return (
    <group>
      {snap.incidents.map((inc) => {
        const n = nodes.get(inc.node_id)
        if (!n) return null
        return <Beacon key={inc.id} n={n} color={SEVERITY[inc.severity]} holo={holo} alpha={focus.nodeAlpha(n)}
          label={!holo && inc.rank && inc.rank <= 5 && inc.severity !== 'resolved' ? `#${inc.rank} ${inc.kind.toUpperCase()}` : null}
          strong={inc.severity === 'critical'} />
      })}
    </group>
  )
}

function Beacon({ n, color, holo, alpha, label, strong }: { n: GNode; color: string; holo: boolean; alpha: number; label: string | null; strong: boolean }) {
  const ring = useRef<THREE.Mesh>(null)
  useFrame(({ clock }) => {
    if (!ring.current) return
    const t = (clock.elapsedTime * (strong ? 1.4 : 0.9)) % 1
    ring.current.scale.setScalar(1 + t * 3)
    ;(ring.current.material as THREE.MeshBasicMaterial).opacity = (1 - t) * Math.max(alpha, 0.15)
  })
  const h = 9
  return (
    <group position={[n.x, n.y, n.z]}>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[0.12, 0.35, h, 8, 1, true]} />
        <meshBasicMaterial color={color} transparent opacity={0.75 * Math.max(alpha, 0.15)} toneMapped={false} depthWrite={false} />
      </mesh>
      <mesh ref={ring} rotation-x={-Math.PI / 2} position={[0, 0.3, 0]}>
        <ringGeometry args={[0.9, 1.2, 32]} />
        <meshBasicMaterial color={color} transparent toneMapped={false} side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
    </group>
  )
}

/* ------------------------------------------------------------ responders */
function Responders({ snap, nodes, holo }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean }) {
  return (
    <group>
      {snap.responders.map((r) => {
        const n = nodes.get(r.node_id)
        if (!n) return null
        return (
          <group key={r.id} position={[n.x + 1.5, n.y + 1.6, n.z + 1.5]}>
            <mesh rotation-y={Math.PI / 4}>
              <boxGeometry args={[1.4, 1.4, 1.4]} />
              <meshBasicMaterial color={ROUTE_RESPONDER} toneMapped={false} wireframe={r.status === 'available'} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}

/* ---------------------------------------------------------------- infra */
const INFRA_COLOR: Record<string, string> = { online: '#9fe8ff', degraded: '#ffb020', damaged: '#ff8a1f', failed: '#ff2a4d', compromised: '#ff2a4d', isolated: '#3dff8f' }
function InfraLayer({ snap, nodes, holo }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean }) {
  const pos = (id: string): V3 | null => {
    const inf = snap.infra.find((i) => i.id === id)
    const n = inf && nodes.get(inf.node_id)
    return n ? [n.x - 2, n.y, n.z - 2] : null
  }
  const showDeps = snap.scenario?.hazard === 'cyberattack' || snap.view.horizon > 0
  return (
    <group>
      {snap.infra.map((i) => {
        const p = pos(i.id)
        if (!p) return null
        const c = INFRA_COLOR[i.status] ?? '#9fe8ff'
        return (
          <group key={i.id} position={p}>
            <mesh position={[0, 2.2, 0]}>
              <coneGeometry args={[0.9, 1.6, 4]} />
              <meshBasicMaterial color={c} toneMapped={false} wireframe={i.status === 'online'} transparent opacity={holo ? 1 : 0.9} />
            </mesh>
            <mesh position={[0, 0.7, 0]}>
              <cylinderGeometry args={[0.08, 0.08, 1.4, 6]} />
              <meshBasicMaterial color={c} toneMapped={false} />
            </mesh>
          </group>
        )
      })}
      {showDeps && snap.infra_deps.map((d) => {
        const a = pos(d.from_id), b = pos(d.to_id)
        if (!a || !b) return null
        const mid: V3 = [(a[0] + b[0]) / 2, 10 + Math.hypot(a[0] - b[0], a[2] - b[2]) * 0.12, (a[2] + b[2]) / 2]
        const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(a[0], 3, a[2]), new THREE.Vector3(...mid), new THREE.Vector3(b[0], 3, b[2]))
        const failed = snap.infra.find((i) => i.id === d.from_id)?.status !== 'online'
        return <Line key={d.from_id + d.to_id} points={curve.getPoints(24)} color={failed ? '#ff2a4d' : '#2d6f86'} lineWidth={holo ? 1.6 : 1} transparent opacity={failed ? 0.8 : 0.35} dashed={!failed} dashSize={0.6} gapSize={0.6} toneMapped={false} />
      })}
    </group>
  )
}

/* ------------------------------------------------------------- forecasts */
function Forecasts({ snap, nodes, holo }: { snap: Snapshot; nodes: Map<string, GNode>; holo: boolean }) {
  const H = snap.view.horizon
  if (!H) return null
  const visible = snap.forecasts.filter((f) => f.horizon_hours <= H && f.status !== 'averted')
  // aftershock zones: show only the latest horizon ≤ H (they decay)
  const aft = visible.filter((f) => f.kind === 'aftershock').sort((a, b) => b.horizon_hours - a.horizon_hours)[0]
  const rest = visible.filter((f) => f.kind !== 'aftershock' && f.kind !== 'weakened_building')
  return (
    <group>
      {aft && <PredictedVolume f={aft} holo={holo} />}
      {rest.map((f) => <PredictedVolume key={f.id} f={f} holo={holo} />)}
    </group>
  )
}

function PredictedVolume({ f, holo }: { f: Forecast; holo: boolean }) {
  const ref = useRef<THREE.Group>(null)
  const color = f.kind === 'fire' ? '#ff6a3d' : PREDICTED
  useFrame(({ clock }) => {
    if (!ref.current) return
    const s = 1 + 0.06 * Math.sin(clock.elapsedTime * 2.2 + f.x)
    ref.current.scale.set(s, 1, s)
  })
  const h = f.kind === 'aftershock' ? 3 : f.kind === 'fire' ? 7 : 12
  const r = Math.max(f.radius || 3, 1.5)
  const op = (0.08 + 0.2 * f.confidence) * (holo ? 1.4 : 1)
  return (
    <group ref={ref} position={[f.x, 0, f.z]}>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[r, r, h, 40, 1, true]} />
        <meshBasicMaterial color={color} transparent opacity={op} side={THREE.DoubleSide} depthWrite={false} toneMapped={false} />
      </mesh>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[r, r, h, 20, 4, true]} />
        <meshBasicMaterial color={color} wireframe transparent opacity={op * 1.6} toneMapped={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position={[0, 0.1, 0]}>
        <ringGeometry args={[r * 0.97, r, 64]} />
        <meshBasicMaterial color={color} transparent opacity={0.9} side={THREE.DoubleSide} toneMapped={false} />
      </mesh>
    </group>
  )
}

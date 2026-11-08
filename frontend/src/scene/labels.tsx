import { useRef } from 'react'
import { useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'
import type { Snapshot } from '../lib/types'
import { SEVERITY } from '../lib/colors'

/** Screen-space labels: a plain DOM overlay positioned each frame by projecting 3D anchors.
 *  (Avoids drei <Html>, which spins up one React root per label.) */
export interface Label { id: string; pos: [number, number, number]; text: string; sub?: string; color: string; boxed?: boolean }

export function sceneLabels(snap: Snapshot | null): Label[] {
  if (!snap) return []
  const nodes = new Map(snap.nodes.map((n) => [n.id, n]))
  const fb = snap.view.focus_building
  const out: Label[] = []
  for (const b of snap.buildings) {
    if (fb && fb !== b.id) continue
    out.push({ id: 'b' + b.id, pos: [b.position.x, b.footprint.h + 2.5, b.position.z], text: b.name.toUpperCase(), color: '#19e6ff' })
  }
  for (const n of snap.nodes.filter((n) => n.kind === 'safe_zone')) {
    const res = snap.resources.find((r) => r.node_id === n.id && r.kind === 'shelter')
    const ok = !snap.scenario || res?.status === 'verified'
    out.push({ id: 's' + n.id, pos: [n.x, 13, n.z], text: '◎ ' + n.label.toUpperCase(), sub: ok ? 'SAFE ZONE' : 'UNVERIFIED', color: ok ? '#3dff8f' : '#ffe14d' })
  }
  for (const r of snap.responders) {
    const n = nodes.get(r.node_id)
    if (n) out.push({ id: 'r' + r.id, pos: [n.x + 1.5, n.y + 4, n.z + 1.5], text: r.name, color: '#ff3df0' })
  }
  for (const inc of snap.incidents) {
    const n = nodes.get(inc.node_id)
    if (!n || !inc.rank || inc.rank > 5 || inc.severity === 'resolved') continue
    if (fb && n.building_id !== fb) continue
    out.push({ id: 'i' + inc.id, pos: [n.x, n.y + 10.5, n.z], text: `#${inc.rank} ${inc.kind.replace('_', ' ').toUpperCase()}`, color: SEVERITY[inc.severity], boxed: true })
  }
  return out
}

const els = new Map<string, HTMLDivElement>()

export function LabelOverlay({ labels }: { labels: Label[] }) {
  return (
    <div className="pointer-events-none absolute inset-0 overflow-hidden">
      {labels.map((l) => (
        <div key={l.id} ref={(el) => { if (el) els.set(l.id, el); else els.delete(l.id) }}
          className={`absolute top-0 left-0 whitespace-nowrap text-center font-mono text-[10px] leading-tight will-change-transform ${l.boxed ? 'border px-1' : ''}`}
          style={{ color: l.color, borderColor: l.color, background: l.boxed ? '#04060bcc' : undefined, textShadow: `0 0 6px ${l.color}`, boxShadow: l.boxed ? `0 0 8px ${l.color}` : undefined, visibility: 'hidden' }}>
          {l.text}{l.sub && <><br /><span className="opacity-80">{l.sub}</span></>}
        </div>
      ))}
    </div>
  )
}

export function LabelProjector({ labels }: { labels: Label[] }) {
  const { camera, size } = useThree()
  const v = useRef(new THREE.Vector3())
  useFrame(() => {
    for (const l of labels) {
      const el = els.get(l.id)
      if (!el) continue
      v.current.set(...l.pos).project(camera)
      if (v.current.z > 1) { el.style.visibility = 'hidden'; continue }
      const x = (v.current.x * 0.5 + 0.5) * size.width, y = (-v.current.y * 0.5 + 0.5) * size.height
      el.style.visibility = 'visible'
      el.style.transform = `translate(-50%, -100%) translate(${x}px, ${y}px)`
    }
  })
  return null
}

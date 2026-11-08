import type { Snapshot } from './types'

export function placeOf(snap: Snapshot, nodeId: string): string {
  const n = snap.nodes.find((x) => x.id === nodeId)
  if (!n) return nodeId
  const b = n.building_id ? snap.buildings.find((x) => x.id === n.building_id) : null
  return b && n.kind !== 'exit' ? `${b.name} · ${n.label}` : n.label
}

export function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${Math.floor(s)}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}

export const AGENT_COLOR: Record<string, string> = {
  'Report Agent': '#19e6ff', 'Situation Agent': '#ffb020', 'Resource Agent': '#ff3df0', 'Comms Agent': '#00ffa3',
  'Simulation Agent': '#b366ff', Orchestrator: '#e8f6ff', Operator: '#3dff8f', 'Mesh Relay': '#9fd8ff',
}

export const SOURCE_ICON: Record<string, string> = { civilian: '☏', beacon: '◉', responder: '✚', third_party: '⌬' }

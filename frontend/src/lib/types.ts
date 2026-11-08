export type EdgeStatus = 'clear' | 'reported_blocked' | 'verified_blocked' | 'unknown'
export type Severity = 'critical' | 'urgent' | 'requested' | 'resolved' | 'disconnected'

export interface Building { id: string; name: string; floors: number; footprint: { w: number; d: number; h: number }; position: { x: number; z: number } }
export interface GNode { id: string; building_id: string | null; floor: number | null; kind: string; x: number; y: number; z: number; label: string }
export interface Edge { id: string; a: string; b: string; length: number; status: EdgeStatus; accessible: number; reserved: number; status_source?: string; status_confidence?: number; status_updated?: string }
export interface Person { id: string; name: string; node_id: string; mobility: 'independent' | 'needs_assist' | 'unknown'; status: string; last_seen: string; location_confidence: number; needs_assessment: number }
export interface Incident { id: string; node_id: string; severity: Severity; kind: string; description: string; source: string; confidence: number; created_at: string; acknowledged: number; person_id: string | null; report_count: number; rank: number | null; score: number | null; rank_reason: string | null }
export interface Responder { id: string; name: string; node_id: string; kind: string; assigned_incident_id: string | null; status: string }
export interface Resource { id: string; name: string; kind: string; node_id: string; capacity: number; status: string }
export interface Infra { id: string; name: string; kind: string; node_id: string; backup_hours: number | null; status: string; vendor: string; network: string }
export interface InfraDep { from_id: string; to_id: string; delay_hours: number }
export interface Forecast { id: string; target_id: string; target_kind: string; hazard: string; kind: string; horizon_hours: number; confidence: number; reason: string; precaution: string; deadline_hours: number; explanation: string; status: 'predicted' | 'occurred' | 'averted'; chain: string[]; x: number; z: number; radius: number; created_at: string }
export interface Approval { id: string; action: string; title: string; payload: Record<string, any>; proposed_by_agent: string; status: 'pending' | 'approved' | 'rejected'; created_at: string; rationale: string }
export interface ToolCall { tool: string; args: Record<string, any>; result_summary: string }
export interface LogEntry { id: number; agent: string; input_summary: string; tool_calls: ToolCall[]; output_summary: string; ts: string; mode: string }
export interface Route { id: string; subject_type: 'person' | 'responder'; subject_id: string; mode: string; path: string[]; length: number; status: string; uses_unknown: number; created_at: string; note: string }
export interface Message { id: string; person_id: string | null; channel: string; text: string; status: 'sent' | 'queued'; ts: string }
export interface Report { id: string; kind: string; text: string; node_id: string; source: string; device: string; status: string; incident_id: string | null; created_at: string }
export interface HazardInfo { id: string; name: string; icon: string; description: string }

export interface Snapshot {
  version: number
  scenario: { hazard: string; name: string; started_at: string; epicenter?: { x: number; z: number } } | null
  view: { horizon: number; focus_building: string | null; focus_floor: number | null }
  offline: boolean
  agent_mode: { mode: 'live' | 'mock'; reason: string }
  buildings: Building[]; nodes: GNode[]; edges: Edge[]; people: Person[]; incidents: Incident[]
  responders: Responder[]; resources: Resource[]; infra: Infra[]; infra_deps: InfraDep[]
  forecasts: Forecast[]; approvals: Approval[]; agent_log: LogEntry[]; routes: Route[]
  messages: Message[]; reports: Report[]; hazards: HazardInfo[]; busy: boolean
}

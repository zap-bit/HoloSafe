# HoloSafe — project memory

> Note: `~/Downloads/CLAUDE.md` belongs to an unrelated project ("Atelier"). Ignore it for HoloSafe (owner confirmed).
> Owner decisions: build/test in AGENT_MODE=mock until the Nemotron key is added to `.env`; Python 3.13 venv at `backend/.venv` (3.11 not installed); local git commits per milestone, no push.

## Milestone task list (keep updated)
- [x] M0 Scaffold — Vite React TS + Tailwind + R3F + drei + zustand + router (/, /holo, /report); FastAPI + SQLite + /health + /ws snapshot; one root command; .env.example
- [x] M1 3D city + hologram — 4 buildings, streets, 2 safe zones, glowing scene, isolate building/floors, people markers, edge colors; /holo 4x Pepper's Ghost cross, calibration keys; cyberpunk shell
- [ ] M2 Data model + scenarios + routing — full SQLite model + seed, hazards/*.json, Trigger/Reset, earthquake effects, networkx route(), animated routes
- [ ] M3 Nemotron agents — 5 tool-calling agents + orchestrator, tools w/ JSON schemas, Agent Activity panel, approvals queue, MOCK fallback + badge, triage ranking
- [ ] M4 Civilian reporting loop — /report phone form → Report Agent → reported_blocked → Comms re-route → approval to verify; incident history; 0.0.0.0 + LAN URL
- [ ] M5 Simulation Agent — cascade_forecast (earthquake + cyberattack), precautions, approvals, predicted volumes, Now/+1h/+6h/+24h slider, scenario switcher
- [ ] M6 Offline mode — toggle, mock agents, IndexedDB cache, queued reports, BroadcastChannel mesh device, sync animation, connectivity indicator
- [ ] M7 Polish — splash with logo glitch, Demo walkthrough button, zero console errors, Reset restores, README + mermaid

---

# SPECIFICATION

# HoloSafe

AI-powered, infrastructure-independent emergency coordination platform with a holographic 3D command center. Hackathon prototype (HackUTD, Nemotron track). Goal: a reliable, visually striking end-to-end demo — not production infrastructure.

Tagline: See. Understand. Evacuate. Coordinate.

## Displays
- `/` — Command Center (laptop): dashboard, incident queue, agent activity log, approval panel, controls.
- `/holo` — Hologram view (second monitor under a Pepper's Ghost pyramid): pure black background, the SAME 3D scene rendered 4 times in a cross layout (top/bottom/left/right), each rotated 90° toward the center, no UI chrome. Both views subscribe to the same live state.
- `/report` — Civilian phone-style report form (blocked route, hazard, distress).

## Stack
- Frontend: React + Vite + TypeScript + Tailwind + React Three Fiber (+ drei). Zustand for state.
- Backend: Python 3.11 + FastAPI + SQLite + WebSockets. networkx for routing and cascades.
- AI: NVIDIA Nemotron via its OpenAI-compatible API. Config in `.env`: NEMOTRON_API_KEY, NEMOTRON_BASE_URL, NEMOTRON_MODEL. Never hardcode keys.
- Monorepo: `/frontend`, `/backend`, root README with run commands.

## Architecture rules (do not break)
1. The 3D scene ONLY renders structured state from the backend. The AI never generates visuals.
2. The LLM never invents routes, zones, or forecasts. It calls tools (routing, cascade, spatial lookup) that return valid results, then reasons over them.
3. High-impact actions (declare area safe, dispatch responders, mark route verified-blocked) go to a human approval queue in the Command Center before taking effect.
4. Every agent call has a deterministic MOCK fallback (`AGENT_MODE=mock`) so the demo works if the API or Wi-Fi dies. Default to live; auto-fall back on error.
5. Disaster types are config, not code paths: `backend/hazards/*.json` (earthquake, cyberattack). Adding a type = adding a config file.
6. Uncertainty is visible: every incident/forecast carries confidence, timestamp, source. "Unknown" is never rendered as "safe". Predicted hazards look different from confirmed ones.

## Data model (SQLite)
- buildings(id, name, footprint, floors, position)
- nodes(id, building_id|null, floor|null, kind[room|corridor|stair|exit|street|safe_zone], x, y, z)
- edges(id, a, b, length, status[clear|reported_blocked|verified_blocked|unknown], accessible bool)
- people(id, node_id, mobility[independent|needs_assist|unknown], status, last_seen, location_confidence)
- incidents(id, node_id, severity[critical|urgent|requested|resolved|disconnected], kind, description, source[civilian|beacon|responder|third_party], confidence, created_at, acknowledged bool)
- responders(id, node_id, kind, assigned_incident_id|null)
- resources(id, kind[shelter|medical|supplies], node_id, capacity)
- infra(id, kind[substation|pump|hospital|cell_tower|traffic|gas_main|data_center], node_id, backup_hours|null, status)
- infra_deps(from_id, to_id, delay_hours)   # to depends on from
- forecasts(id, target_id, hazard, horizon_hours, confidence, reason, precaution, status[predicted|occurred|averted])
- approvals(id, action, payload_json, proposed_by_agent, status[pending|approved|rejected])
- agent_log(id, agent, input_summary, tool_calls_json, output_summary, ts)

Severity colors: critical=red, urgent=orange, requested/uncertain=yellow, resolved=green, disconnected=grey. Edge status: clear=cyan, reported_blocked=amber dashed, verified_blocked=red, unknown=dim grey.

## Agents (one Nemotron service, five specialized workflows, all tool-calling)
1. Report Agent — ingest raw reports, classify, extract location/severity, dedupe, assign confidence. Tools: spatial_lookup, create_incident, update_edge_status.
2. Situation Agent — maintain world state per hazard config; rank incidents by severity, time sensitivity, isolation, vulnerability, accessibility, confidence — NOT report volume. Unknown mobility → needs assessment.
3. Resource Agent — Pathway B: match responders to trapped/injured people, compute responder access routes, propose dispatches (approval required). Tools: route(mode=responder), propose_action.
4. Comms Agent — Pathway A: per-person evacuation instructions, re-route on hazard change, keep civilian routes out of responder corridors, broadcast via WebSocket, queue messages when "offline". Tools: route(mode=civilian), notify.
5. Simulation Agent — forecast cascading fallout. Calls cascade_forecast(hazard, epicenter|initial_failures, horizons=[1,6,24]) which propagates over infra_deps + hazard rules; then explains results and attaches a concrete precaution + deadline to each forecast. Precautions that change operations go to approvals.

An orchestrator routes events: new report → Report → Situation → (Resource, Comms) in parallel; scenario start or major new failure → Simulation. Every step is written to agent_log and streamed to the Command Center.

## Design direction
Cyberpunk command center, NOT generic AI-dashboard UI. Layered translucent panels, scanlines/glow, animated overlays, neon accents on near-black, non-generic display fonts (e.g. Orbitron/Rajdhani/Share Tech Mono from Google Fonts — pick a distinctive pairing). Opening splash: the fire-dragon/drone illustration (placeholder at `frontend/public/logo.*` — owner will drop in the real asset) which also serves as the logo. Hologram view: high contrast, glowing wireframe buildings, bright markers — the pyramid needs bright-on-black.

## Demo script (everything serves this)
1. Intact 3D city in hologram. 2. Trigger earthquake. 3. Distress reports appear. 4. Agents triage (log visible). 5. Independent people get routes. 6. Trapped people enter rescue queue; responder routes proposed → approve. 7. Civilian reports blocked stairwell from /report. 8. Routes recalculate, hologram updates. 9. Simulation shows next fallout zones on a time slider (+1h/+6h/+24h) with precautions. 10. Toggle "offline": local features keep working, messages queue, then sync on reconnect. Bonus: switch to cyberattack scenario, same agents.

## Working conventions
- Small, working increments. Run the app and fix errors before declaring a phase done.
- Seed data lives in `backend/seed/` and is reloadable with one command/button ("Reset scenario").
- Keep a `make dev` or single `npm run dev` that starts both servers.

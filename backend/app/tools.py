"""Agent tools. Real, deterministic Python functions with JSON schemas.

Agents (live Nemotron or mock) can ONLY change the world through these. The LLM never invents
routes, zones or forecasts: it calls route / spatial_lookup / cascade_forecast and reasons over results.
"""
import json
import math
import re
import uuid
from datetime import datetime, timezone

from . import db, routing, scenario, state

SEV_ORDER = ["resolved", "disconnected", "requested", "urgent", "critical"]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:6]}"


def _node(nid: str) -> dict | None:
    return db.q1("SELECT * FROM nodes WHERE id=?", (nid,))


def place(nid: str) -> str:
    """Human label with building prefix, e.g. 'Meridian Tower · Room 305'."""
    n = _node(nid)
    if not n:
        return nid
    if n["building_id"] and n["kind"] != "exit":
        b = db.q1("SELECT name FROM buildings WHERE id=?", (n["building_id"],))
        return f"{b['name']} · {n['label']}"
    return n["label"]


def _people_near(node: dict, radius: float, exclude: str | None = None) -> list[dict]:
    out = []
    for p in db.q("SELECT p.*, n.x, n.y, n.z, n.building_id, n.floor FROM people p JOIN nodes n ON n.id=p.node_id"):
        if p["id"] == exclude or p["status"] == "rescued":  # rescued people have left; they can't help or be helped here
            continue
        if node["building_id"] and (p["building_id"] != node["building_id"] or p["floor"] != node["floor"]):
            continue
        if math.dist((p["x"], p["z"]), (node["x"], node["z"])) <= radius:
            out.append(p)
    return out


# ------------------------------------------------------------------ spatial_lookup
def spatial_lookup(node_id: str | None = None, text: str | None = None, building_id: str | None = None) -> dict:
    """Resolve a location. `text` may contain 'room 305', 'stairwell 1', 'lobby', 'floor 2'."""
    node = _node(node_id) if node_id else None
    bid = building_id or (node["building_id"] if node else None)
    resolved = node
    how = "device location" if node else None
    if text:
        t = text.lower()
        m = re.search(r"room\s*(\d)(\d{2})", t)
        if m and bid:
            cand = _node(f"{bid}-F{int(m.group(1))}-R{int(m.group(2))}")
            if cand:
                resolved, how = cand, f"parsed '{m.group(0)}'"
        m = re.search(r"stair(?:well|s|case)?\s*(\d)", t)
        if m and bid and not (how or "").startswith("parsed"):
            fl = node["floor"] if node and node["floor"] else 1
            cand = _node(f"{bid}-F{fl}-S{m.group(1)}")
            if cand:
                resolved, how = cand, f"parsed '{m.group(0)}'"
        if "lobby" in t and bid and not (how or "").startswith("parsed"):
            cand = _node(f"{bid}-F1-C2")
            if cand:
                resolved, how = cand, "parsed 'lobby'"
    if not resolved:
        return {"ok": False, "reason": "location not resolved"}
    edges = db.q("SELECT id, a, b, status, accessible FROM edges WHERE a=? OR b=?", (resolved["id"], resolved["id"]))
    near = _people_near(resolved, 12)
    b = db.q1("SELECT name FROM buildings WHERE id=?", (resolved["building_id"],)) if resolved["building_id"] else None
    return {
        "ok": True, "node_id": resolved["id"], "label": place(resolved["id"]), "kind": resolved["kind"],
        "building": b["name"] if b else None, "floor": resolved["floor"], "resolved_by": how or "node id",
        "people_within_12m": len(near), "people_here": [p["id"] for p in near if p["node_id"] == resolved["id"]],
        "edges": [{"id": e["id"], "status": e["status"]} for e in edges],
    }


# ------------------------------------------------------------------ create_incident
def _same_place(a: dict, b: dict) -> bool:
    if a["id"] == b["id"]:
        return True
    if a["building_id"] != b["building_id"]:
        return False
    if a["building_id"] and a["floor"] != b["floor"]:
        return False
    return math.dist((a["x"], a["z"]), (b["x"], b["z"])) <= (8 if a["building_id"] else 10)


def create_incident(node_id: str, severity: str, kind: str, description: str, source: str = "civilian",
                    confidence: float = 0.6, person_id: str | None = None) -> dict:
    """Create an incident, or merge into an open one of the same kind at the same place (dedupe)."""
    node = _node(node_id)
    if not node:
        return {"ok": False, "reason": f"unknown node {node_id}"}
    severity = severity if severity in SEV_ORDER else "requested"
    for inc in db.q("SELECT * FROM incidents WHERE kind=? AND severity!='resolved'", (kind,)):
        other = _node(inc["node_id"])
        if other and _same_place(node, other) and (not person_id or not inc["person_id"] or inc["person_id"] == person_id):
            sev = max(inc["severity"], severity, key=SEV_ORDER.index)
            conf = round(min(0.97, 1 - (1 - inc["confidence"]) * (1 - confidence * 0.5)), 2)
            db.update("incidents", inc["id"], report_count=inc["report_count"] + 1, severity=sev, confidence=conf,
                      person_id=inc["person_id"] or person_id)
            state.broadcast()
            return {"ok": True, "incident_id": inc["id"], "merged": True, "report_count": inc["report_count"] + 1,
                    "severity": sev, "confidence": conf}
    if not person_id and kind in ("distress", "trapped", "medical"):
        here = db.q("SELECT id FROM people WHERE node_id=? AND status IN ('trapped','injured')", (node_id,))
        person_id = here[0]["id"] if here else None
    iid = _id("INC")
    db.insert("incidents", dict(id=iid, node_id=node_id, severity=severity, kind=kind, description=description[:240],
                                source=source, confidence=round(confidence, 2), created_at=now(), acknowledged=0,
                                person_id=person_id, report_count=1, rank=None, score=None, rank_reason=None))
    state.broadcast()
    return {"ok": True, "incident_id": iid, "merged": False, "severity": severity, "node": node["label"]}


# ------------------------------------------------------------------ update_edge_status
def resolve_blocked_edge(node_id: str) -> str | None:
    """Which edge does 'blocked at <node>' mean? Stair → the flight below it; else first edge toward an exit."""
    node = _node(node_id)
    if not node:
        return None
    if node["kind"] == "stair" and node["floor"]:
        sid = node_id.rsplit("-", 1)[1]
        for f in (node["floor"] - 1, node["floor"] + 1):
            other = f"{node['building_id']}-F{f}-{sid}"
            e = db.q1("SELECT id FROM edges WHERE (a=? AND b=?) OR (a=? AND b=?)", (other, node_id, node_id, other))
            if e:
                return e["id"]
    r = routing.route(node_id, "exit" if node["building_id"] else "safe_zone")
    if r["ok"] and r["edge_ids"]:
        return r["edge_ids"][0]
    e = db.q1("SELECT id FROM edges WHERE (a=? OR b=?) AND status='clear'", (node_id, node_id))
    return e["id"] if e else None


def update_edge_status(status: str, edge_id: str | None = None, node_id: str | None = None,
                       source: str = "civilian", confidence: float = 0.6, note: str = "") -> dict:
    """Set an edge's status. Unverified sources can only REPORT a blockage; verification needs human approval."""
    if not edge_id and node_id:
        edge_id = resolve_blocked_edge(node_id)
    e = db.q1("SELECT * FROM edges WHERE id=?", (edge_id,)) if edge_id else None
    if not e:
        return {"ok": False, "reason": "edge not found"}
    requires_approval = False
    if status == "verified_blocked" and source not in ("responder", "operator"):
        status, requires_approval = "reported_blocked", True
    if e["status"] == "verified_blocked" and status == "reported_blocked":
        return {"ok": True, "edge_id": e["id"], "old": e["status"], "new": e["status"], "note": "already verified blocked"}
    db.update("edges", e["id"], status=status, status_source=source, status_confidence=confidence, status_updated=now())
    affected = [r["id"] for r in db.q("SELECT id, path_json FROM routes WHERE status IN ('active','proposed')")
                if _route_uses(json.loads(r["path_json"]), e["a"], e["b"])]
    state.broadcast()
    return {"ok": True, "edge_id": e["id"], "between": [e["a"], e["b"]], "old": e["status"], "new": status,
            "affected_routes": len(affected), "verification_needs_approval": requires_approval or status == "reported_blocked"}


def _route_uses(path: list[str], a: str, b: str) -> bool:
    return any({x, y} == {a, b} for x, y in zip(path, path[1:]))


# ------------------------------------------------------------------ route
def route(mode: str = "civilian", subject_id: str | None = None, from_node: str | None = None,
          to_kind: str = "safe_zone", to_node: str | None = None, commit: bool = True, note: str = "") -> dict:
    """Compute a route. subject_id = person (P..) or responder (R..). Civilian routes are stored as active;
    responder routes are stored as PROPOSED until a dispatch is approved."""
    mobility = "independent"
    if subject_id and subject_id.startswith("P"):
        p = db.q1("SELECT * FROM people WHERE id=?", (subject_id,))
        if not p:
            return {"ok": False, "reason": "unknown person"}
        from_node, mobility = from_node or p["node_id"], p["mobility"]
        if mobility == "unknown":
            return {"ok": False, "reason": "mobility unknown — needs assessment before independent routing"}
    elif subject_id and subject_id.startswith("R"):
        r = db.q1("SELECT * FROM responders WHERE id=?", (subject_id,))
        if not r:
            return {"ok": False, "reason": "unknown responder"}
        from_node, mode = from_node or r["node_id"], "responder"
    if not from_node:
        return {"ok": False, "reason": "from_node or subject_id required"}
    res = routing.route(from_node, to_kind, mode, mobility, to_node)
    if res["ok"] and commit and subject_id:
        stype = "person" if subject_id.startswith("P") else "responder"
        db.ex("UPDATE routes SET status='superseded' WHERE subject_id=? AND status IN ('active','proposed')", (subject_id,))
        rid = _id("RT")
        db.insert("routes", dict(id=rid, subject_type=stype, subject_id=subject_id, mode=mode, path_json=json.dumps(res["path"]),
                                 length=res["length_m"], status="active" if stype == "person" else "proposed",
                                 uses_unknown=int(res["uses_unknown"]), created_at=now(), note=note))
        res["route_id"] = rid
        state.broadcast()
    res["describe"] = describe_path(res.get("path") or [], mobility) if res["ok"] else None
    if res["ok"]:  # keep tool output compact for the LLM
        res["path"] = res["path"] if len(res["path"]) <= 8 else res["path"][:3] + ["…"] + res["path"][-3:]
        res.pop("edge_ids", None)
    return res


def describe_path(path: list[str], mobility: str = "independent") -> str:
    if not path:
        return ""
    nodes = {n["id"]: n for n in db.q("SELECT * FROM nodes")}
    steps, last = [], None
    for nid in path:
        n = nodes[nid]
        tag = None
        if n["kind"] == "stair" and (last is None or last["kind"] != "stair"):
            tag = f"Stairwell {nid.rsplit('-S', 1)[1]}"
        elif n["kind"] == "exit":
            tag = n["label"].split(" · ")[-1]
        elif n["kind"] == "street" and (last is None or last["kind"] != "street"):
            tag = n["label"]
        elif n["kind"] == "safe_zone":
            tag = n["label"]
        if tag and (not steps or steps[-1] != tag):
            steps.append(tag)
        last = n
    s = " → ".join(steps)
    return ("Assisted: " + s) if mobility == "needs_assist" else s


# ------------------------------------------------------------------ rank_incidents
def rank_incidents() -> dict:
    """Score open incidents by severity, isolation, vulnerability, time sensitivity, accessibility and
    confidence. Report VOLUME is deliberately ignored."""
    cfg = scenario.current_cfg() or {}
    T = cfg.get("triage") or {"severity_weight": {"critical": 100, "urgent": 60, "requested": 25, "disconnected": 15, "resolved": 0},
                             "isolation_weight": 30, "vulnerability_weight": 20, "time_weight": 15,
                             "accessibility_weight": 15, "confidence_floor": 0.55, "isolation_radius": 12}
    ranked = []
    db.ex("UPDATE incidents SET rank=NULL, score=NULL WHERE severity='resolved'")
    for inc in db.q("SELECT * FROM incidents WHERE severity!='resolved'"):
        node = _node(inc["node_id"])
        person = db.q1("SELECT * FROM people WHERE id=?", (inc["person_id"],)) if inc["person_id"] else None
        others = _people_near(node, T["isolation_radius"], exclude=inc["person_id"])
        isolation = 1.0 if not others else 0.5 if len(others) == 1 else 0.0
        vul = 0.0
        if person:
            vul = max(vul, {"needs_assist": 1.0, "unknown": 0.7}.get(person["mobility"], 0.0),
                      0.6 if person["status"] in ("trapped", "injured") else 0.0)
        if inc["kind"] in ("needs_assessment",):
            vul = max(vul, 0.7)
        if inc["kind"] == "assisted_evac":
            vul = 1.0
        text = (inc["description"] or "").lower()
        time_s = 1.0 if inc["severity"] == "critical" or any(w in text for w in ("gas", "fire", "smoke", "no movement", "pinned")) \
            else 0.8 if inc["kind"] in ("trapped", "distress") else 0.3
        acc = 0.0
        if node["building_id"]:
            r = routing.route(node["id"], "exit")
            acc = 1.0 if not r["ok"] else 0.6 if r["uses_unknown"] else 0.0
        base = (T["severity_weight"].get(inc["severity"], 20) + T["isolation_weight"] * isolation +
                T["vulnerability_weight"] * vul + T["time_weight"] * time_s + T["accessibility_weight"] * acc)
        score = round(base * (T["confidence_floor"] + (1 - T["confidence_floor"]) * inc["confidence"]), 1)
        reasons = [inc["severity"]]
        n_near, R = len(others), T["isolation_radius"]
        reasons.append(f"isolated (0 people within {R}m)" if n_near == 0
                       else f"{n_near} {'person' if n_near == 1 else 'people'} within {R}m")
        if vul >= 0.7:
            reasons.append("vulnerable" if inc["kind"] != "needs_assessment" else "mobility unknown")
        if acc == 1.0:
            reasons.append("no passable exit")
        elif acc > 0:
            reasons.append("only unverified access")
        reasons.append(f"conf {inc['confidence']:.2f}")
        if inc["report_count"] > 1:
            reasons.append(f"{inc['report_count']} reports (volume ignored)")
        ranked.append((score, inc, " · ".join(reasons)))
    ranked.sort(key=lambda x: -x[0])
    for i, (score, inc, why) in enumerate(ranked, start=1):
        db.update("incidents", inc["id"], rank=i, score=score, rank_reason=why)
    state.broadcast()
    return {"ok": True, "ranked": [{"rank": i, "incident_id": inc["id"], "kind": inc["kind"], "severity": inc["severity"],
                                    "node": inc["node_id"], "place": place(inc["node_id"]), "person_id": inc["person_id"], "score": s, "why": why,
                                    "acknowledged": bool(inc["acknowledged"])}
                                   for i, (s, inc, why) in enumerate(ranked, start=1)]}


# ------------------------------------------------------------------ propose_action
def propose_action(action: str, title: str, payload: dict, rationale: str = "", agent: str = "agent") -> dict:
    """Queue a high-impact action for human approval. Nothing changes until a human approves."""
    key = json.dumps(payload, sort_keys=True)
    for a in db.q("SELECT * FROM approvals WHERE action=? AND status='pending'", (action,)):
        if json.dumps(json.loads(a["payload_json"]), sort_keys=True) == key:
            return {"ok": True, "approval_id": a["id"], "duplicate": True}
    aid = _id("APR")
    db.insert("approvals", dict(id=aid, action=action, title=title, payload_json=json.dumps(payload),
                                proposed_by_agent=agent, status="pending", created_at=now(), rationale=rationale[:400]))
    state.broadcast()
    return {"ok": True, "approval_id": aid, "status": "pending_human_approval"}


# ------------------------------------------------------------------ notify
def notify(text: str, person_id: str | None = None, channel: str = "push") -> dict:
    """Send (or queue, when offline) a message to one person or a broadcast."""
    offline = db.get_meta("offline", False)
    mid = _id("MSG")
    db.insert("messages", dict(id=mid, person_id=person_id, channel="broadcast" if not person_id else channel,
                               text=text[:300], status="queued" if offline else "sent", ts=now()))
    state.broadcast()
    return {"ok": True, "message_id": mid, "status": "queued" if offline else "sent"}


# ------------------------------------------------------------------ cascade_forecast
def cascade_forecast(hazard: str | None = None, horizons: list[float] | None = None) -> dict:
    from . import cascade
    return cascade.cascade_forecast(hazard, horizons or [1, 6, 24])


# ------------------------------------------------------------------ registry + JSON schemas
FUNCS = {f.__name__: f for f in (spatial_lookup, create_incident, update_edge_status, rank_incidents, route,
                                 propose_action, notify, cascade_forecast)}

SCHEMAS = {
    "spatial_lookup": {"description": "Resolve a location from a node id and/or free text (e.g. 'room 305', 'stairwell 1', 'lobby'). Returns node, building, floor, nearby people and adjacent edge statuses.",
                       "parameters": {"type": "object", "properties": {
                           "node_id": {"type": "string", "description": "device/selected node id"},
                           "text": {"type": "string", "description": "raw report text to parse for a location"},
                           "building_id": {"type": "string"}}}},
    "create_incident": {"description": "Create an incident (auto-dedupes with an open incident of the same kind at the same place).",
                        "parameters": {"type": "object", "required": ["node_id", "severity", "kind", "description"], "properties": {
                            "node_id": {"type": "string"},
                            "severity": {"type": "string", "enum": ["critical", "urgent", "requested"]},
                            "kind": {"type": "string", "enum": ["distress", "trapped", "medical", "hazard", "blocked_route", "needs_assessment", "assisted_evac"]},
                            "description": {"type": "string"},
                            "source": {"type": "string", "enum": ["civilian", "beacon", "responder", "third_party"]},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "person_id": {"type": "string"}}}},
    "update_edge_status": {"description": "Mark a route segment's status. Give edge_id, or node_id to block the flight/segment at that node. Civilian sources can only set reported_blocked; verified_blocked requires human approval.",
                           "parameters": {"type": "object", "required": ["status"], "properties": {
                               "status": {"type": "string", "enum": ["reported_blocked", "unknown", "clear"]},
                               "edge_id": {"type": "string"}, "node_id": {"type": "string"},
                               "source": {"type": "string"}, "confidence": {"type": "number"}, "note": {"type": "string"}}}},
    "rank_incidents": {"description": "Deterministically score and rank all open incidents (severity, isolation, vulnerability, time sensitivity, accessibility, confidence — NOT report count).",
                       "parameters": {"type": "object", "properties": {}}},
    "route": {"description": "Compute a safe route on the building/street graph. Civilian mode excludes blocked edges, avoids unknown edges and responder corridors; responder mode may breach the final obstacle.",
              "parameters": {"type": "object", "properties": {
                  "mode": {"type": "string", "enum": ["civilian", "responder"]},
                  "subject_id": {"type": "string", "description": "person id (P..) or responder id (R..); route is stored for them"},
                  "from_node": {"type": "string"},
                  "to_kind": {"type": "string", "enum": ["safe_zone", "exit", "node"]},
                  "to_node": {"type": "string", "description": "destination node when to_kind=node"},
                  "note": {"type": "string"}}}},
    "propose_action": {"description": "Queue a high-impact action for human approval (dispatch_responder, verify_blocked, declare_safe, or an operational precaution).",
                       "parameters": {"type": "object", "required": ["action", "title", "payload"], "properties": {
                           "action": {"type": "string", "enum": ["dispatch_responder", "verify_blocked", "declare_safe", "shut_gas_valve", "fuel_resupply", "isolate_network", "restrict_entry"]},
                           "title": {"type": "string"}, "payload": {"type": "object"}, "rationale": {"type": "string"}}}},
    "notify": {"description": "Send a message to a person (person_id) or a broadcast (no person_id). Queued automatically when offline.",
               "parameters": {"type": "object", "required": ["text"], "properties": {
                   "text": {"type": "string"}, "person_id": {"type": "string"}, "channel": {"type": "string"}}}},
    "cascade_forecast": {"description": "Deterministic cascade simulation over the infrastructure dependency graph + hazard rules. Returns forecasts with horizon_hours, confidence and reason.",
                         "parameters": {"type": "object", "properties": {
                             "hazard": {"type": "string"},
                             "horizons": {"type": "array", "items": {"type": "number"}}}}},
}


def openai_tools(names: list[str]) -> list[dict]:
    return [{"type": "function", "function": {"name": n, **SCHEMAS[n]}} for n in names]


def call(name: str, args: dict) -> dict:
    fn = FUNCS[name]
    try:
        return fn(**args)
    except TypeError as e:
        return {"ok": False, "reason": f"bad arguments: {e}"}

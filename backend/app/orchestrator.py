"""Event routing:  new report → Report → Situation → (Resource ∥ Comms);  scenario start / major failure → Simulation.
Also executes human-approved actions (the ONLY path by which high-impact actions change state)."""
import asyncio
import json

from . import agents, db, scenario, state, tools
from seed.seed import load_seed

_lock = asyncio.Lock()
_tasks: set[asyncio.Task] = set()
_epoch = 0  # bumps on reset so stale background tasks stop touching state


def _spawn(coro) -> None:
    t = asyncio.get_event_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


def _busy(v: bool) -> None:
    db.set_meta("busy", v)
    state.broadcast()


def reset() -> None:
    global _epoch
    _epoch += 1
    for t in list(_tasks):
        t.cancel()
    offline = db.get_meta("offline", False)
    load_seed(scenario.hazard_summaries())
    db.set_meta("offline", offline)
    agents.refresh_mode_badge()
    state.broadcast()


async def trigger(hazard: str) -> None:
    cfg = scenario.load_hazards().get(hazard)
    if not cfg:
        raise ValueError(f"unknown hazard {hazard}")
    reset()
    _spawn(_run_scenario(cfg, _epoch))


async def _run_scenario(cfg: dict, epoch: int) -> None:
    async with _lock:
        _busy(True)
        try:
            lines = scenario.apply_hazard(cfg)
            agents.log_event("Orchestrator", f"SCENARIO START · {cfg['name']}",
                             f"Applied {len(lines)} T+0 effects from hazards/{cfg['id']}.json: " + "; ".join(lines[:6]))
            state.broadcast()
            await asyncio.sleep(1.2)
            for rep in cfg.get("reports", []):
                if epoch != _epoch:
                    return
                _store_report(rep, device="scenario-feed")
                await agents.report_agent(rep)
                await asyncio.sleep(0.6)
            await _after_reports("scenario start", initial=True, epoch=epoch)
            if epoch == _epoch:
                await _simulate("scenario start")
        finally:
            if epoch == _epoch:
                _busy(False)


async def _after_reports(trigger: str, initial: bool = False, epoch: int | None = None) -> None:
    await agents.situation_agent(trigger)
    if epoch is not None and epoch != _epoch:
        return
    await asyncio.gather(agents.resource_agent(trigger), agents.comms_agent(trigger, initial=initial))


async def _simulate(trigger: str) -> None:
    sim = getattr(agents, "simulation_agent", None)
    if sim:
        await sim(trigger)


def _store_report(rep: dict, device: str, status: str = "processed") -> str:
    rid = tools._id("REP")
    db.insert("reports", dict(id=rid, kind=rep.get("kind") or "auto", text=rep["text"], node_id=rep["node_id"],
                              source=rep.get("source", "civilian"), device=device, status=status, incident_id=None,
                              created_at=tools.now()))
    return rid


async def handle_report(rep: dict, device: str = "phone") -> dict:
    """Civilian report from /report (or synced from the offline queue)."""
    rid = _store_report(rep, device=device, status="processing")
    state.broadcast()
    epoch = _epoch
    async with _lock:
        _busy(True)
        try:
            res = await agents.report_agent(rep)
            inc = (res.get("incident") or {}).get("incident_id")
            db.update("reports", rid, status="processed", incident_id=inc)
            trig = f"new report {rid}"
            await _after_reports(trig, epoch=epoch)
            if rep.get("kind") == "hazard" or "gas" in rep["text"].lower() or "fire" in rep["text"].lower():
                await _simulate(trig)
        finally:
            _busy(False)
    return {"ok": True, "report_id": rid, "incident_id": inc}


# ------------------------------------------------------------------ approvals
async def decide(approval_id: str, approve: bool) -> dict:
    a = db.q1("SELECT * FROM approvals WHERE id=?", (approval_id,))
    if not a or a["status"] != "pending":
        return {"ok": False, "reason": "not pending"}
    db.update("approvals", approval_id, status="approved" if approve else "rejected")
    p = json.loads(a["payload_json"])
    if not approve:
        if a["action"] == "dispatch_responder" and p.get("route_id"):
            db.update("routes", p["route_id"], status="superseded")
        agents.log_event("Operator", f"REJECTED · {a['title']}", "No state change.")
        state.broadcast()
        return {"ok": True}
    msg = await _execute(a["action"], p)
    agents.log_event("Operator", f"APPROVED · {a['title']}", msg)
    state.broadcast()
    return {"ok": True, "result": msg}


async def _execute(action: str, p: dict) -> str:
    if action == "dispatch_responder":
        r = db.q1("SELECT * FROM responders WHERE id=?", (p["responder_id"],))
        inc = db.q1("SELECT * FROM incidents WHERE id=?", (p["incident_id"],))
        route = db.q1("SELECT * FROM routes WHERE id=?", (p.get("route_id"),)) if p.get("route_id") else None
        if not route or route["status"] == "superseded":
            rt = tools.route(mode="responder", subject_id=r["id"], to_kind="node", to_node=inc["node_id"])
            route = db.q1("SELECT * FROM routes WHERE id=?", (rt.get("route_id"),)) if rt.get("ok") else None
        if not route:
            return "No responder route available — dispatch held."
        db.update("routes", route["id"], status="active")
        db.update("responders", r["id"], status="en_route", assigned_incident_id=inc["id"])
        db.update("incidents", inc["id"], acknowledged=1)
        _spawn(_move_responder(r["id"], json.loads(route["path_json"]), inc["id"], route["id"], _epoch))
        return f"{r['name']} en route ({route['length']} m)."
    if action == "verify_blocked":
        e = db.q1("SELECT * FROM edges WHERE id=?", (p["edge_id"],))
        db.update("edges", e["id"], status="verified_blocked", status_source="responder", status_confidence=0.95,
                  status_updated=tools.now())
        await state.event("edge_pulse", {"edge_id": e["id"]})
        _spawn(_comms_followup(f"edge {e['id']} verified blocked"))
        return f"{e['id']} now VERIFIED BLOCKED."
    if action == "declare_safe":
        db.update("resources", p["resource_id"], status="verified")
        return "Shelter verified safe."
    # operational precautions from the Simulation Agent
    averted = 0
    for fid in p.get("forecast_ids", []):
        db.update("forecasts", fid, status="averted")
        averted += 1
    if action == "shut_gas_valve":
        db.ex("UPDATE infra SET status='isolated' WHERE kind='gas_main' AND status!='online'")
    if action == "isolate_network" and p.get("infra_id"):
        db.update("infra", p["infra_id"], status="isolated")
    return f"Precaution in effect; {averted} forecast(s) marked averted."


async def _comms_followup(trigger: str) -> None:
    async with _lock:
        await agents.comms_agent(trigger)


async def _move_responder(rid: str, path: list[str], incident_id: str, route_id: str, epoch: int) -> None:
    for nid in path[1:]:
        await asyncio.sleep(0.55)
        if epoch != _epoch:
            return
        db.update("responders", rid, node_id=nid)
        state.broadcast()
    db.update("responders", rid, status="on_scene")
    db.update("routes", route_id, status="completed")
    await asyncio.sleep(2.5)
    if epoch != _epoch:
        return
    inc = db.q1("SELECT * FROM incidents WHERE id=?", (incident_id,))
    db.update("incidents", incident_id, severity="resolved")
    if inc and inc["person_id"]:
        db.update("people", inc["person_id"], status="rescued")
    r = db.q1("SELECT name FROM responders WHERE id=?", (rid,))
    agents.log_event("Orchestrator", f"{r['name']} on scene", f"Incident {incident_id} resolved — person rescued, handed to EMS.")
    tools.rank_incidents()
    db.update("responders", rid, status="available", assigned_incident_id=None)
    state.broadcast()

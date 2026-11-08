import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from . import agents, db, orchestrator, scenario, state  # noqa: E402

app = FastAPI(title="HoloSafe")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    db.conn()
    if not db.q1("SELECT id FROM nodes LIMIT 1"):
        orchestrator.reset()
    db.set_meta("hazards", scenario.hazard_summaries())
    db.set_meta("busy", False)
    agents.refresh_mode_badge()


@app.get("/health")
def health():
    m, why = agents.configured_mode()
    return {"ok": True, "agent_mode": m, "reason": why}


@app.get("/api/state")
def get_state():
    return state.snapshot()


@app.post("/api/scenario/reset")
async def reset():
    orchestrator.reset()
    return {"ok": True}


class TriggerIn(BaseModel):
    hazard: str = "earthquake"


@app.post("/api/scenario/trigger")
async def trigger(t: TriggerIn):
    try:
        await orchestrator.trigger(t.hazard)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}


class ReportIn(BaseModel):
    text: str
    node_id: str
    kind: str | None = None          # blocked_route | hazard | distress (form category = hint)
    source: str = "civilian"
    device: str = "phone"
    person_id: str | None = None


@app.post("/api/report")
async def report(r: ReportIn):
    if not db.q1("SELECT id FROM nodes WHERE id=?", (r.node_id,)):
        raise HTTPException(400, "unknown node")
    rep = r.model_dump(exclude={"device"})
    return await orchestrator.handle_report(rep, device=r.device)


@app.post("/api/approvals/{aid}/{decision}")
async def decide(aid: str, decision: str):
    if decision not in ("approve", "reject"):
        raise HTTPException(400, "approve|reject")
    return await orchestrator.decide(aid, decision == "approve")


class OfflineIn(BaseModel):
    offline: bool


@app.post("/api/offline")
async def set_offline(o: OfflineIn):
    db.set_meta("offline", o.offline)
    agents.refresh_mode_badge()
    flushed = 0
    if not o.offline:
        flushed = db.q1("SELECT COUNT(*) n FROM messages WHERE status='queued'")["n"]
        db.ex("UPDATE messages SET status='sent' WHERE status='queued'")
        if flushed:
            agents.log_event("Comms Agent", "LINK RESTORED", f"Delivered {flushed} queued message(s).")
    state.broadcast()
    return {"ok": True, "flushed": flushed}


class ViewIn(BaseModel):
    horizon: float | None = None
    focus_building: str | None = None
    focus_floor: int | None = None


@app.post("/api/view")
async def set_view(v: ViewIn):
    cur = db.get_meta("view", {})
    cur.update(v.model_dump(exclude_unset=True))
    db.set_meta("view", cur)
    state.broadcast()
    return cur


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await state.register(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        state.unregister(ws)

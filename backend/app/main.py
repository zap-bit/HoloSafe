import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from . import db, state  # noqa: E402
from seed.seed import load_seed  # noqa: E402

app = FastAPI(title="HoloSafe")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    db.conn()
    if not db.q1("SELECT id FROM nodes LIMIT 1"):
        load_seed()


@app.get("/health")
def health():
    return {"ok": True, "agent_mode": os.getenv("AGENT_MODE", "live")}


@app.get("/api/state")
def get_state():
    return state.snapshot()


@app.post("/api/scenario/reset")
async def reset():
    load_seed()
    state.broadcast()
    return {"ok": True}


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

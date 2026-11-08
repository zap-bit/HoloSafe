import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from . import db, state  # noqa: E402

app = FastAPI(title="HoloSafe")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
async def startup():
    db.conn()


@app.get("/health")
def health():
    return {"ok": True, "agent_mode": os.getenv("AGENT_MODE", "live")}


@app.get("/api/state")
def get_state():
    return state.snapshot()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await state.register(ws)
    try:
        while True:
            await ws.receive_text()  # clients only listen; keepalive pings land here
    except WebSocketDisconnect:
        pass
    finally:
        state.unregister(ws)

"""Snapshot assembly + WebSocket broadcast hub."""
import asyncio
import json
from fastapi import WebSocket
from . import db

_clients: set[WebSocket] = set()
_pending: asyncio.Task | None = None
_version = 0


def snapshot() -> dict:
    return {
        "version": _version,
        "scenario": db.get_meta("scenario", None),
        "view": db.get_meta("view", {"horizon": 0, "focus_building": None, "focus_floor": None}),
        "offline": db.get_meta("offline", False),
        "agent_mode": db.get_meta("agent_mode", {"mode": "mock", "reason": "init"}),
        "buildings": [dict(b, footprint=json.loads(b["footprint"]), position=json.loads(b["position"]))
                      for b in db.q("SELECT * FROM buildings")],
        "nodes": db.q("SELECT * FROM nodes"),
        "edges": db.q("SELECT * FROM edges"),
        "people": db.q("SELECT * FROM people"),
        "incidents": db.q("SELECT * FROM incidents ORDER BY COALESCE(rank, 999), created_at"),
        "responders": db.q("SELECT * FROM responders"),
        "resources": db.q("SELECT * FROM resources"),
        "infra": db.q("SELECT * FROM infra"),
        "infra_deps": db.q("SELECT * FROM infra_deps"),
        "forecasts": [dict(f, chain=json.loads(f.pop("chain_json") or "[]")) for f in db.q("SELECT * FROM forecasts ORDER BY horizon_hours")],
        "approvals": [dict(a, payload=json.loads(a.pop("payload_json") or "{}"))
                      for a in db.q("SELECT * FROM approvals ORDER BY created_at DESC")],
        "agent_log": [dict(l, tool_calls=json.loads(l.pop("tool_calls_json") or "[]"))
                      for l in db.q("SELECT * FROM agent_log ORDER BY id DESC LIMIT 120")],
        "routes": [dict(r, path=json.loads(r.pop("path_json"))) for r in db.q("SELECT * FROM routes WHERE status!='superseded'")],
        "messages": db.q("SELECT * FROM messages ORDER BY ts DESC LIMIT 80"),
        "reports": db.q("SELECT * FROM reports ORDER BY created_at DESC LIMIT 60"),
        "hazards": db.get_meta("hazards", []),
        "busy": db.get_meta("busy", False),
    }


async def register(ws: WebSocket) -> None:
    await ws.accept()
    _clients.add(ws)
    await ws.send_text(json.dumps({"type": "snapshot", "data": snapshot()}))


def unregister(ws: WebSocket) -> None:
    _clients.discard(ws)


async def _send_all(msg: str) -> None:
    dead = []
    for ws in list(_clients):
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


async def _flush() -> None:
    global _version
    await asyncio.sleep(0.05)  # coalesce bursts of changes into one snapshot
    _version += 1
    await _send_all(json.dumps({"type": "snapshot", "data": snapshot()}))


def broadcast() -> None:
    """Schedule a (debounced) snapshot broadcast. Safe to call many times."""
    global _pending
    if _pending is None or _pending.done():
        _pending = asyncio.get_event_loop().create_task(_flush())


async def event(kind: str, data: dict) -> None:
    """Fire-and-forget UI event (e.g. edge pulse, sync animation)."""
    await _send_all(json.dumps({"type": "event", "kind": kind, "data": data}))

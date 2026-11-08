"""Hazard configs (backend/hazards/*.json) — disaster types are data, not code paths."""
import json
from datetime import datetime, timezone
from pathlib import Path

from . import db

HAZARD_DIR = Path(__file__).resolve().parent.parent / "hazards"


def load_hazards() -> dict[str, dict]:
    return {p.stem: json.loads(p.read_text()) for p in sorted(HAZARD_DIR.glob("*.json"))}


def hazard_summaries() -> list[dict]:
    return [{"id": h["id"], "name": h["name"], "icon": h.get("icon", ""), "description": h.get("description", "")}
            for h in load_hazards().values()]


def current_cfg() -> dict | None:
    sc = db.get_meta("scenario")
    return load_hazards().get(sc["hazard"]) if sc else None


def _edge_between(a: str, b: str) -> dict | None:
    return db.q1("SELECT * FROM edges WHERE (a=? AND b=?) OR (a=? AND b=?)", (a, b, b, a))


def apply_hazard(cfg: dict) -> list[str]:
    """Apply the config's immediate (T+0) effects. Returns human-readable effect lines for the log."""
    t = datetime.now(timezone.utc).isoformat()
    db.set_meta("scenario", {"hazard": cfg["id"], "name": cfg["name"], "started_at": t, "epicenter": cfg.get("epicenter")})
    lines = []
    fx = cfg.get("effects", {})
    for e in fx.get("edges", []):
        edge = _edge_between(e["a"], e["b"])
        if not edge:
            lines.append(f"!! config edge {e['a']}~{e['b']} not found")
            continue
        db.update("edges", edge["id"], status=e["status"], status_source=e.get("source", "third_party"),
                  status_confidence=e.get("confidence", 0.5), status_updated=t)
        lines.append(f"{edge['id']} → {e['status']} ({e.get('note', '')})")
    for i in fx.get("infra", []):
        db.update("infra", i["id"], status=i["status"])
        lines.append(f"{i['id']} → {i['status']}")
    for p in fx.get("people", []):
        db.update("people", p["id"], status=p["status"])
    if cfg.get("shelters_unverified"):
        db.ex("UPDATE resources SET status='unverified' WHERE kind='shelter'")
    return lines


def evacuate_buildings(cfg: dict) -> set[str] | None:
    ev = cfg.get("evacuate", "all")
    return None if ev == "all" else set(ev)

"""SQLite access. One connection, used only from the asyncio event loop thread."""
import json
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "holosafe.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS buildings(id TEXT PRIMARY KEY, name TEXT, footprint TEXT, floors INTEGER, position TEXT);
CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY, building_id TEXT, floor INTEGER, kind TEXT, x REAL, y REAL, z REAL, label TEXT);
CREATE TABLE IF NOT EXISTS edges(id TEXT PRIMARY KEY, a TEXT, b TEXT, length REAL, status TEXT, accessible INTEGER, reserved INTEGER DEFAULT 0, status_source TEXT, status_confidence REAL, status_updated TEXT);
CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY, name TEXT, node_id TEXT, mobility TEXT, status TEXT, last_seen TEXT, location_confidence REAL, needs_assessment INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS incidents(id TEXT PRIMARY KEY, node_id TEXT, severity TEXT, kind TEXT, description TEXT, source TEXT, confidence REAL, created_at TEXT, acknowledged INTEGER DEFAULT 0, person_id TEXT, report_count INTEGER DEFAULT 1, rank INTEGER, score REAL, rank_reason TEXT);
CREATE TABLE IF NOT EXISTS responders(id TEXT PRIMARY KEY, name TEXT, node_id TEXT, kind TEXT, assigned_incident_id TEXT, status TEXT);
CREATE TABLE IF NOT EXISTS resources(id TEXT PRIMARY KEY, name TEXT, kind TEXT, node_id TEXT, capacity INTEGER, status TEXT);
CREATE TABLE IF NOT EXISTS infra(id TEXT PRIMARY KEY, name TEXT, kind TEXT, node_id TEXT, backup_hours REAL, status TEXT, vendor TEXT, network TEXT);
CREATE TABLE IF NOT EXISTS infra_deps(from_id TEXT, to_id TEXT, delay_hours REAL);
CREATE TABLE IF NOT EXISTS forecasts(id TEXT PRIMARY KEY, target_id TEXT, target_kind TEXT, hazard TEXT, kind TEXT, horizon_hours REAL, confidence REAL, reason TEXT, precaution TEXT, deadline_hours REAL, explanation TEXT, status TEXT, chain_json TEXT, x REAL, z REAL, radius REAL, created_at TEXT);
CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, action TEXT, title TEXT, payload_json TEXT, proposed_by_agent TEXT, status TEXT, created_at TEXT, rationale TEXT);
CREATE TABLE IF NOT EXISTS agent_log(id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, input_summary TEXT, tool_calls_json TEXT, output_summary TEXT, ts TEXT, mode TEXT);
CREATE TABLE IF NOT EXISTS routes(id TEXT PRIMARY KEY, subject_type TEXT, subject_id TEXT, mode TEXT, path_json TEXT, length REAL, status TEXT, uses_unknown INTEGER, created_at TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY, person_id TEXT, channel TEXT, text TEXT, status TEXT, ts TEXT);
CREATE TABLE IF NOT EXISTS reports(id TEXT PRIMARY KEY, kind TEXT, text TEXT, node_id TEXT, source TEXT, device TEXT, status TEXT, incident_id TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
"""

TABLES = ["buildings", "nodes", "edges", "people", "incidents", "responders", "resources", "infra",
          "infra_deps", "forecasts", "approvals", "agent_log", "routes", "messages", "reports", "meta"]

_conn: sqlite3.Connection | None = None


def conn() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
    return _conn


def q(sql: str, args: tuple = ()) -> list[dict]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def q1(sql: str, args: tuple = ()) -> dict | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def ex(sql: str, args: tuple = ()) -> None:
    conn().execute(sql, args)
    conn().commit()


def insert(table: str, row: dict) -> None:
    cols = ",".join(row.keys())
    ph = ",".join("?" for _ in row)
    conn().execute(f"INSERT OR REPLACE INTO {table}({cols}) VALUES({ph})", tuple(row.values()))
    conn().commit()


def update(table: str, id_: str, **fields) -> None:
    sets = ",".join(f"{k}=?" for k in fields)
    conn().execute(f"UPDATE {table} SET {sets} WHERE id=?", (*fields.values(), id_))
    conn().commit()


def wipe() -> None:
    c = conn()
    for t in TABLES:
        c.execute(f"DELETE FROM {t}")
    c.execute("DELETE FROM sqlite_sequence WHERE name='agent_log'") if c.execute(
        "SELECT name FROM sqlite_master WHERE name='sqlite_sequence'").fetchone() else None
    c.commit()


def get_meta(key: str, default=None):
    r = q1("SELECT value FROM meta WHERE key=?", (key,))
    return json.loads(r["value"]) if r else default


def set_meta(key: str, value) -> None:
    ex("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, json.dumps(value)))

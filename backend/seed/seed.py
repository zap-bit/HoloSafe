"""Deterministic seed for the HoloSafe demo city. `python -m seed.seed` (from backend/) reloads it.

Coordinates: x/z on the ground plane (metres-ish), y = height. Floors are 1-based (1 = ground).
"""
import json
import math
from datetime import datetime, timezone

from app import db

FH = 4.0  # floor height

BUILDINGS = [
    dict(id="B1", name="Meridian Tower", cx=-25, cz=-15, w=24, d=16, floors=4,
         corr=[-8, -3, 3, 8], stairs=[("S1", -11), ("S2", 11)],
         exits=[("E1", -12, 0, False, "West exit (steps)"), ("E2", 12, 0, True, "East exit"), ("E3", 0, 8, True, "Main lobby doors")]),
    dict(id="B2", name="Helix Labs", cx=25, cz=-15, w=18, d=14, floors=2,
         corr=[-4, 4], stairs=[("S1", -7)],
         exits=[("E1", 0, 7, True, "Lab entrance")]),
    dict(id="B3", name="Civic Hospital", cx=-25, cz=25, w=22, d=14, floors=3,
         corr=[-6, 0, 6], stairs=[("S1", -9.5), ("S2", 9.5)],
         exits=[("E1", 0, -7, True, "ER entrance"), ("E2", -11, 0, True, "Ambulance bay")]),
    dict(id="B4", name="Nova Data Center", cx=25, cz=25, w=18, d=14, floors=2,
         corr=[-4, 4], stairs=[("S1", 7)],
         exits=[("E1", 0, -7, True, "Loading dock")]),
]

VX = {-55: ("W", "West Ave"), 0: ("C", "Central Ave"), 55: ("E", "East Ave")}
HZ = {-40: ("N", "North St"), 5: ("M", "Main St"), 45: ("S", "South St")}
XN = {-55: "W", -25: "WC", 0: "C", 25: "EC", 55: "E"}
ZN = {-40: "N", -15: "NM", 5: "M", 25: "SM", 45: "S"}
V_POINTS = [-40, -15, 5, 25, 45]
H_POINTS = [-55, -25, 0, 25, 55]

SAFE_ZONES = [("SZ1", "North Plaza", -25, -60, "ST-WC-N"), ("SZ2", "East Park", 80, 5, "ST-E-M")]

PEOPLE = [
    ("P01", "Ava Chen", "B1-F1-C2", "independent"), ("P02", "Marcus Lee", "B1-F1-C3", "independent"),
    ("P03", "Priya Nair", "B1-F1-R2", "independent"),
    ("P04", "Diego Ruiz", "B1-F2-R1", "independent"), ("P05", "Hana Sato", "B1-F2-R2", "independent"),
    ("P06", "Unregistered visitor", "B1-F2-R3", "unknown"), ("P07", "Omar Haddad", "B1-F2-R7", "independent"),
    ("P08", "Grace Kim", "B1-F3-R5", "independent"), ("P09", "Leo Martins", "B1-F3-R6", "independent"),
    ("P10", "Sara Novak", "B1-F3-R1", "independent"), ("P11", "Ben Okafor", "B1-F3-R2", "independent"),
    ("P12", "Ruth Alvarez", "B1-F4-R1", "needs_assist"), ("P13", "Ivan Petrov", "B1-F4-R3", "independent"),
    ("P14", "Mei Wong", "B1-F4-R8", "independent"),
    ("P15", "Tom Becker", "B2-F1-R1", "independent"), ("P16", "Aisha Bello", "B2-F1-R4", "independent"),
    ("P17", "Dr. Elena Voss", "B2-F2-R3", "independent"),
    ("P18", "Patient · Bed 12", "B3-F1-R2", "needs_assist"), ("P19", "Patient · Bed 27", "B3-F2-R3", "needs_assist"),
    ("P20", "Patient · Bed 41", "B3-F3-R5", "needs_assist"), ("P21", "Nurse J. Park", "B3-F1-C2", "independent"),
    ("P22", "Kai Turner", "B4-F1-R2", "independent"), ("P23", "Contractor (badge unread)", "B4-F2-R4", "unknown"),
    ("P24", "Nina Rossi", "ST-C-M", "independent"), ("P25", "Unidentified pedestrian", "ST-W-S", "unknown"),
]

RESPONDERS = [("R1", "Engine 7", "ST-C-N", "fire_rescue"), ("R2", "Medic 3", "ST-C-S", "ems"),
              ("R3", "USAR Team 1", "ST-E-N", "search_rescue")]

RESOURCES = [("RS1", "North Plaza Shelter", "shelter", "SZ1", 300), ("RS2", "East Park Shelter", "shelter", "SZ2", 200),
             ("RS3", "Civic ER", "medical", "B3-F1-C2", 40), ("RS4", "Supply cache", "supplies", "SZ2", 500)]

INFRA = [
    ("SUB-A", "Westside Substation", "substation", "ST-W-S", None, "VoltNet SCADA", "GRID-OT"),
    ("SUB-B", "Eastside Substation", "substation", "ST-E-N", None, "VoltNet SCADA", "GRID-OT"),
    ("PUMP-1", "North Pump Station", "pump", "ST-W-N", None, "AquaLogic PLC", "WATER-OT"),
    ("PUMP-2", "South Pump Station", "pump", "ST-E-S", None, "AquaLogic PLC", "WATER-OT"),
    ("HOSP-1", "Civic Hospital power", "hospital", "B3-F1-C1", 8, "MedGrid", "HOSP-NET"),
    ("CT-1", "Cell tower · Central", "cell_tower", "ST-C-M", 4, "SkyLink", "TELCO"),
    ("CT-2", "Cell tower · East", "cell_tower", "ST-E-M", 4, "SkyLink", "TELCO"),
    ("CT-3", "Cell tower · West", "cell_tower", "ST-W-M", 4, "SkyLink", "TELCO"),
    ("TRAF-1", "Signals · Central/North", "traffic", "ST-C-N", None, "CityFlow", "CITY-OPS"),
    ("TRAF-2", "Signals · Main St East", "traffic", "ST-EC-M", None, "CityFlow", "CITY-OPS"),
    ("GAS-1", "Main St gas main", "gas_main", "ST-WC-M", None, "MetroGas", "GAS-OT"),
    ("DC-1", "Nova Data Center", "data_center", "B4-F1-C1", 1, "NovaCloud", "CITY-OPS"),
]

INFRA_DEPS = [  # (from, to, delay_hours): `to` depends on `from`
    ("SUB-A", "PUMP-1", 0), ("SUB-A", "HOSP-1", 0), ("SUB-A", "CT-1", 0), ("SUB-A", "CT-3", 0), ("SUB-A", "TRAF-1", 0),
    ("SUB-B", "PUMP-2", 0), ("SUB-B", "CT-2", 0), ("SUB-B", "TRAF-2", 0), ("SUB-B", "DC-1", 0),
    ("DC-1", "TRAF-1", 0.5), ("DC-1", "TRAF-2", 0.5), ("PUMP-1", "HOSP-1", 2),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _dist(a, b) -> float:
    return math.dist((a["x"], a["y"], a["z"]), (b["x"], b["y"], b["z"]))


def build_graph():
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(id_, kind, x, y, z, label, b=None, f=None):
        nodes[id_] = dict(id=id_, building_id=b, floor=f, kind=kind, x=x, y=y, z=z, label=label)

    def edge(a, b, accessible=True, reserved=False, length=None):
        edges.append(dict(id=f"{a}~{b}", a=a, b=b, length=round(length or _dist(nodes[a], nodes[b]), 2),
                          status="clear", accessible=int(accessible), reserved=int(reserved),
                          status_source=None, status_confidence=None, status_updated=None))

    # --- buildings
    for B in BUILDINGS:
        bid, cx, cz = B["id"], B["cx"], B["cz"]
        for f in range(1, B["floors"] + 1):
            y = (f - 1) * FH
            cids = []
            for i, ox in enumerate(B["corr"], start=1):
                cid = f"{bid}-F{f}-C{i}"
                node(cid, "corridor", cx + ox, y, cz, f"Floor {f} corridor {i}", bid, f)
                cids.append(cid)
                for side, oz, rn in (("north", -B["d"] / 4, 2 * i - 1), ("south", B["d"] / 4, 2 * i)):
                    rid = f"{bid}-F{f}-R{rn}"
                    node(rid, "room", cx + ox, y, cz + oz, f"Room {f}{rn:02d}", bid, f)
                    edge(rid, cid)
            for a, b in zip(cids, cids[1:]):
                edge(a, b)
            for sid, ox in B["stairs"]:
                nid = f"{bid}-F{f}-{sid}"
                node(nid, "stair", cx + ox, y, cz, f"Stairwell {sid[1:]} · floor {f}", bid, f)
                near = min(cids, key=lambda c: abs(nodes[c]["x"] - (cx + ox)))
                edge(nid, near)
                if f > 1:
                    edge(f"{bid}-F{f - 1}-{sid}", nid, accessible=False, length=FH * 1.6)
        for eid, ox, oz, acc, label in B["exits"]:
            xid = f"{bid}-{eid}"
            node(xid, "exit", cx + ox, 0, cz + oz, f"{B['name']} · {label}", bid, 1)
            f1 = [n for n in nodes.values() if n["building_id"] == bid and n["floor"] == 1 and n["kind"] in ("corridor", "stair")]
            near = min(f1, key=lambda n: _dist(n, nodes[xid]))
            edge(near["id"], xid, accessible=acc)

    # --- streets
    def sid(x, z):
        return f"ST-{XN[x]}-{ZN[z]}"

    def slabel(x, z):
        if x in VX and z in HZ:
            return f"{VX[x][1]} & {HZ[z][1]}"
        if x in VX:
            return f"{VX[x][1]} (block {ZN[z]})"
        return f"{HZ[z][1]} (block {XN[x]})"

    for x in VX:
        for z in V_POINTS:
            node(sid(x, z), "street", x, 0, z, slabel(x, z))
        for z1, z2 in zip(V_POINTS, V_POINTS[1:]):
            edge(sid(x, z1), sid(x, z2), reserved=(x == 0))
    for z in HZ:
        for x in H_POINTS:
            if sid(x, z) not in nodes:
                node(sid(x, z), "street", x, 0, z, slabel(x, z))
        for x1, x2 in zip(H_POINTS, H_POINTS[1:]):
            edge(sid(x1, z), sid(x2, z))

    streets = [n for n in nodes.values() if n["kind"] == "street"]
    for n in list(nodes.values()):
        if n["kind"] == "exit":
            near = min(streets, key=lambda s: _dist(s, n))
            edge(n["id"], near["id"])

    for zid, name, x, z, link in SAFE_ZONES:
        node(zid, "safe_zone", x, 0, z, name)
        edge(link, zid)
    return nodes, edges


def load_seed(hazards: list | None = None) -> None:
    db.wipe()
    nodes, edges = build_graph()
    c = db.conn()
    for B in BUILDINGS:
        c.execute("INSERT INTO buildings VALUES(?,?,?,?,?)", (
            B["id"], B["name"], json.dumps({"w": B["w"], "d": B["d"], "h": B["floors"] * FH}), B["floors"],
            json.dumps({"x": B["cx"], "z": B["cz"]})))
    c.executemany("INSERT INTO nodes VALUES(:id,:building_id,:floor,:kind,:x,:y,:z,:label)", list(nodes.values()))
    c.executemany("INSERT INTO edges VALUES(:id,:a,:b,:length,:status,:accessible,:reserved,:status_source,"
                  ":status_confidence,:status_updated)", edges)
    t = now()
    for pid, name, nid, mob in PEOPLE:
        assert nid in nodes, nid
        c.execute("INSERT INTO people VALUES(?,?,?,?,?,?,?,?)", (pid, name, nid, mob, "ok", t,
                                                                 0.6 if mob == "unknown" else 0.95, 0))
    for rid, name, nid, kind in RESPONDERS:
        c.execute("INSERT INTO responders VALUES(?,?,?,?,?,?)", (rid, name, nid, kind, None, "available"))
    for rid, name, kind, nid, cap in RESOURCES:
        c.execute("INSERT INTO resources VALUES(?,?,?,?,?,?)", (rid, name, kind, nid, cap, "open"))
    for row in INFRA:
        assert row[3] in nodes, row
        c.execute("INSERT INTO infra VALUES(?,?,?,?,?,?,?,?)", (row[0], row[1], row[2], row[3], row[4], "online", row[5], row[6]))
    c.executemany("INSERT INTO infra_deps VALUES(?,?,?)", INFRA_DEPS)
    c.commit()
    db.set_meta("scenario", None)
    db.set_meta("view", {"horizon": 0, "focus_building": None, "focus_floor": None})
    db.set_meta("busy", False)
    if hazards is not None:
        db.set_meta("hazards", hazards)


if __name__ == "__main__":
    from app import scenario
    load_seed(scenario.hazard_summaries())
    print("seeded:", {t: db.q1(f"SELECT COUNT(*) n FROM {t}")["n"] for t in ("nodes", "edges", "people", "infra")})

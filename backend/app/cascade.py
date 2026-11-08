"""cascade_forecast — deterministic fallout simulation over infra_deps + hazard-config rules.
The Simulation Agent only explains and attaches precautions; it never invents forecasts."""
import heapq
import json
import math

import networkx as nx

from . import db, scenario, state, tools

KIND_OF = {"hospital": "power_loss", "data_center": "power_loss", "cell_tower": "comms_loss", "pump": "water_loss",
           "traffic": "traffic_loss", "substation": "power_loss", "gas_main": "power_loss"}


def _horizon(t: float, horizons: list[float]) -> float | None:
    return next((h for h in sorted(horizons) if t <= h + 1e-9), None)


def _infra_pos(inf: dict, nodes: dict) -> tuple[float, float]:
    n = nodes[inf["node_id"]]
    return n["x"] - 2, n["z"] - 2


def _infra_cascade(cfg: dict, horizons: list[float], nodes: dict) -> list[dict]:
    C = cfg.get("cascade", {})
    infra = {i["id"]: i for i in db.q("SELECT * FROM infra")}
    deps = db.q("SELECT * FROM infra_deps")
    G = nx.DiGraph()
    for d in deps:
        G.add_edge(d["from_id"], d["to_id"], delay=d["delay_hours"])
    roots: dict[str, tuple[float, float, str]] = {}  # id → (fail time, confidence, why)
    for i in infra.values():
        if i["status"] in ("failed", "compromised"):
            roots[i["id"]] = (0.0, 1.0, f"{i['name']} {i['status']} at T+0")
    out = []
    vec = cfg.get("attack_vector")
    if vec:  # cyber: same vendor / network as the initial target is at risk — spreads by system, not geography
        for i in infra.values():
            if i["id"] in roots or i["status"] == "isolated":
                continue
            if i["vendor"] == vec.get("vendor") or i["network"] == vec.get("network"):
                h = C.get("same_vendor_horizon", 6)
                conf = C.get("same_vendor_confidence", 0.55)
                roots[i["id"]] = (float(h), conf, f"same {'vendor ' + vec['vendor'] if i['vendor'] == vec.get('vendor') else 'network ' + vec['network']} as the compromised target")
                x, z = _infra_pos(i, nodes)
                out.append(dict(target_id=i["id"], target_kind="infra", kind="compromise", horizon_hours=_horizon(h, horizons),
                                eta_hours=h, confidence=conf, chain=[i["id"]], x=x, z=z, radius=5,
                                reason=f"{i['name']} runs {i['vendor']} on {i['network']} — same attack surface as the initial target; lateral movement expected within ~{h}h."))
    # earliest-failure propagation (any failed supplier takes a dependent down once its backup runs out)
    best: dict[str, tuple[float, float, list[str], str]] = {}
    pq = [(t, rid, conf, [rid], why) for rid, (t, conf, why) in roots.items()]
    heapq.heapify(pq)
    while pq:
        t, nid, conf, chain, why = heapq.heappop(pq)
        if nid in best:
            continue
        best[nid] = (t, conf, chain, why)
        if nid not in G:
            continue
        for _, dep, data in G.out_edges(nid, data=True):
            di = infra[dep]
            if dep in best or di["status"] in ("isolated",) or dep in roots:
                continue
            backup = di["backup_hours"] or 0
            td = t + data["delay"] + backup
            why_d = (f"loses supply from {infra[nid]['name']} (down T+{t:g}h)"
                     + (f" after {data['delay']:g}h lag" if data["delay"] else "")
                     + (f"; {backup:g}h backup → fails ~T+{td:g}h" if backup else f" → fails ~T+{td:g}h (no backup)"))
            heapq.heappush(pq, (td, dep, conf * C.get("hop_decay", 0.85), chain + [dep], why_d))
    for nid, (t, conf, chain, why) in best.items():
        if nid in roots and roots[nid][0] == 0:
            continue  # already failed — confirmed, not predicted
        if nid in roots:
            continue  # vendor-risk root already emitted above
        h = _horizon(t, horizons)
        if h is None:
            continue
        inf = infra[nid]
        x, z = _infra_pos(inf, nodes)
        out.append(dict(target_id=nid, target_kind="infra", kind=KIND_OF.get(inf["kind"], "power_loss"), horizon_hours=h,
                        eta_hours=t, confidence=round(conf * C.get("infra_base_confidence", 0.9), 2), chain=chain,
                        x=x, z=z, radius=4, reason=f"{inf['name']} {why}."))
    return out


def _earthquake_rules(cfg: dict, horizons: list[float], nodes: dict) -> list[dict]:
    C = cfg.get("cascade", {})
    ep = cfg.get("epicenter")
    out = []
    if not ep:
        return out
    a = C.get("aftershock")
    if a:
        for k, h in enumerate(sorted(horizons)):
            p = a["p0"] * math.exp(-h / a["tau_h"])
            out.append(dict(target_id="zone:aftershock", target_kind="zone", kind="aftershock", horizon_hours=h, eta_hours=h,
                            confidence=round(p, 2), chain=[], x=ep["x"], z=ep["z"], radius=round(a["radius_m"] * a["radius_decay"] ** k, 1),
                            reason=f"Aftershock probability decays with time (Omori): P(M5+ within {h:g}h) ≈ {p:.0%}; zone shrinks to {a['radius_m'] * a['radius_decay'] ** k:.0f} m."))
    wr = C.get("weakened_radius_m")
    if wr:
        damaged = {e["a"].split("-")[0] for e in db.q("SELECT a FROM edges WHERE status='verified_blocked' AND a LIKE 'B%'")}
        for b in db.q("SELECT * FROM buildings"):
            pos, fp = json.loads(b["position"]), json.loads(b["footprint"])
            d = math.dist((pos["x"], pos["z"]), (ep["x"], ep["z"]))
            if b["id"] in damaged or d <= wr + max(fp["w"], fp["d"]) / 2:
                conf = 0.6 if b["id"] in damaged else 0.4
                out.append(dict(target_id=b["id"], target_kind="building", kind="weakened_building", horizon_hours=6, eta_hours=6,
                                confidence=conf, chain=[], x=pos["x"], z=pos["z"], radius=max(fp["w"], fp["d"]) / 2,
                                reason=f"{b['name']}: {'critical internal damage' if b['id'] in damaged else 'within the strong-shaking radius'} "
                                       f"({d:.0f} m from epicentre); aftershocks may cause partial collapse."))
    f = C.get("fire")
    if f:
        src = db.q1("SELECT * FROM infra WHERE id=?", (f["source_infra"],))
        if src and src["status"] == "damaged":
            S = nx.Graph()
            for e in db.q("SELECT e.a, e.b FROM edges e JOIN nodes na ON na.id=e.a JOIN nodes nb ON nb.id=e.b "
                          "WHERE na.kind='street' AND nb.kind='street'"):
                S.add_edge(e["a"], e["b"])
            hops = nx.single_source_shortest_path_length(S, src["node_id"], cutoff=max(f["spread_hops"].values()))
            for h in sorted(horizons):
                maxhop = f["spread_hops"].get(str(int(h)), None)
                if maxhop is None:
                    continue
                for nid, hop in hops.items():
                    if hop > maxhop:
                        continue
                    n = nodes[nid]
                    out.append(dict(target_id=nid, target_kind="node", kind="fire", horizon_hours=h, eta_hours=h,
                                    confidence=round(f["ignition_confidence"] * f["hop_decay"] ** hop, 2), chain=[src["id"]],
                                    x=n["x"], z=n["z"], radius=5 + 2 * hop,
                                    reason=(f"Gas main break ({src['name']}) + ignition sources → fire at the break" if hop == 0 else
                                            f"Fire spread {hop} block(s) from the gas main break along the street grid")))
    return out


def cascade_forecast(hazard: str | None, horizons: list[float]) -> dict:
    cfg = scenario.load_hazards().get(hazard) if hazard else scenario.current_cfg()
    cfg = cfg or scenario.current_cfg()
    if not cfg:
        return {"ok": False, "reason": "no active scenario"}
    nodes = {n["id"]: n for n in db.q("SELECT * FROM nodes")}
    fc = _infra_cascade(cfg, horizons, nodes) + _earthquake_rules(cfg, horizons, nodes)
    prev = {f["id"]: f for f in db.q("SELECT * FROM forecasts")}
    db.ex("DELETE FROM forecasts WHERE status='predicted'")
    t = tools.now()
    rows = []
    for f in fc:
        fid = f"FC-{f['kind']}-{f['target_id']}-{f['horizon_hours']:g}".replace(":", "_")
        old = prev.get(fid)
        if old and old["status"] != "predicted":
            rows.append(dict(old, eta_hours=f["eta_hours"]))  # keep averted/occurred status (and precaution text)
            continue
        row = dict(id=fid, target_id=f["target_id"], target_kind=f["target_kind"], hazard=cfg["id"], kind=f["kind"],
                   horizon_hours=f["horizon_hours"], confidence=f["confidence"], reason=f["reason"],
                   precaution=(old or {}).get("precaution"), deadline_hours=(old or {}).get("deadline_hours"),
                   explanation=(old or {}).get("explanation"), status="predicted", chain_json=json.dumps(f["chain"]),
                   x=f["x"], z=f["z"], radius=f["radius"], created_at=t)
        db.insert("forecasts", row)
        rows.append(dict(row, eta_hours=f["eta_hours"]))
    state.broadcast()
    return {"ok": True, "hazard": cfg["id"], "count": len(rows),
            "forecasts": [{"id": r["id"], "kind": r["kind"], "target": r["target_id"], "horizon_h": r["horizon_hours"],
                           "eta_h": r.get("eta_hours"), "confidence": r["confidence"], "status": r["status"], "reason": r["reason"]}
                          for r in rows]}

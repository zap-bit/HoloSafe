"""Deterministic routing over the building/street graph (networkx). The LLM never invents routes."""
import networkx as nx

from . import db

PENALTY_UNKNOWN = 40          # avoid unverified edges whenever an alternative exists
PENALTY_INACCESSIBLE = 6      # needs_assist: strongly prefer step-free edges
PENALTY_RESERVED_CIVILIAN = 60  # keep civilians out of responder corridors
BONUS_RESERVED_RESPONDER = 0.6
PENALTY_REPORTED_RESPONDER = 4  # responders may pass reported-but-unverified blockages (they assess/clear)
SPEED = {"civilian": 1.2, "responder": 2.2}  # m/s (inside buildings dominates)


def _graph(mode: str, mobility: str, breach_target: str | None = None) -> nx.Graph:
    G = nx.Graph()
    for e in db.q("SELECT * FROM edges"):
        st, w = e["status"], e["length"]
        breach = False
        if st == "verified_blocked":
            # responders can force/breach a verified obstacle (locked door, light debris) at a high cost
            if mode == "responder":
                w *= 10
                breach = True
            else:
                continue
        if st == "reported_blocked":
            if mode == "civilian":
                continue
            w *= PENALTY_REPORTED_RESPONDER
        if st == "unknown":
            w *= PENALTY_UNKNOWN
        if e["reserved"]:
            w *= PENALTY_RESERVED_CIVILIAN if mode == "civilian" else BONUS_RESERVED_RESPONDER
        if mobility == "needs_assist" and not e["accessible"]:
            w *= PENALTY_INACCESSIBLE
        G.add_edge(e["a"], e["b"], weight=w, id=e["id"], status=st, length=e["length"],
                   reserved=e["reserved"], accessible=e["accessible"], breach=breach)
    return G


def route(from_node: str, to_kind: str = "safe_zone", mode: str = "civilian", mobility: str = "independent",
          to_node: str | None = None, avoid_nodes: list[str] | None = None) -> dict:
    """Shortest safe path. to_kind: safe_zone | exit | node (requires to_node)."""
    if to_node:
        targets = [to_node]
    else:
        targets = [n["id"] for n in db.q("SELECT id FROM nodes WHERE kind=?", (to_kind,))]
    G = _graph(mode, mobility, breach_target=to_node if mode == "responder" else None)
    for n in avoid_nodes or []:
        if n in G and n != from_node and n not in targets:
            G.remove_node(n)
    if from_node not in G:
        return {"ok": False, "reason": "origin has no passable edges (isolated)", "from": from_node}
    dist, paths = nx.single_source_dijkstra(G, from_node, weight="weight")
    cands = [t for t in targets if t in dist]
    if not cands:
        return {"ok": False, "reason": f"no passable {mode} route to {to_node or to_kind}", "from": from_node}
    best = min(cands, key=dist.get)
    path = paths[best]
    eds = [G.edges[a, b] for a, b in zip(path, path[1:])]
    length = round(sum(e["length"] for e in eds), 1)
    return {
        "ok": True, "from": from_node, "target": best, "path": path, "edge_ids": [e["id"] for e in eds],
        "length_m": length, "eta_min": round(length / SPEED[mode] / 60, 1),
        "uses_unknown": any(e["status"] == "unknown" for e in eds),
        "uses_reported_blocked": any(e["status"] == "reported_blocked" for e in eds),
        "uses_reserved": any(e["reserved"] for e in eds),
        "inaccessible_edges": sum(1 for e in eds if not e["accessible"]),
        "breach_required": any(e["breach"] for e in eds),
    }

"""Five specialised agent workflows on ONE OpenAI-compatible Nemotron client.

Each agent = optional deterministic pre-steps (tool calls) + an LLM tool-calling loop (live) or a
deterministic MOCK step. Live runs auto-fall back to MOCK on API error, timeout, or when the model
skips a required tool. Every run is written to agent_log and streamed to the Command Center.
"""
import asyncio
import json
import os
import re
from typing import Callable

from . import db, routing, scenario, state, tools

_client = None


def _cfg():
    return {
        "key": os.getenv("NEMOTRON_API_KEY", "").strip(),
        "base": os.getenv("NEMOTRON_BASE_URL", "https://integrate.api.nvidia.com/v1").strip(),
        "model": os.getenv("NEMOTRON_MODEL", "nvidia/nemotron-3.5-super-vl-120b-a12b").strip(),
        "mode": os.getenv("AGENT_MODE", "live").strip().lower(),
        "timeout": float(os.getenv("AGENT_TIMEOUT", "20")),
    }


def configured_mode() -> tuple[str, str]:
    c = _cfg()
    if db.get_meta("offline", False):
        return "mock", "OFFLINE"
    if c["mode"] == "mock":
        return "mock", "AGENT_MODE=mock"
    if not c["key"]:
        return "mock", "no API key"
    return "live", c["model"]


def refresh_mode_badge() -> None:
    m, why = configured_mode()
    db.set_meta("agent_mode", {"mode": m, "reason": why})


def client():
    global _client
    if _client is None:
        from openai import AsyncOpenAI
        c = _cfg()
        _client = AsyncOpenAI(api_key=c["key"], base_url=c["base"], max_retries=0)
    return _client


# ---------------------------------------------------------------- run bookkeeping
def _summ(res) -> str:
    if not isinstance(res, dict):
        return str(res)[:160]
    if not res.get("ok", True):
        return "✗ " + str(res.get("reason", ""))[:150]
    keys = ["incident_id", "merged", "report_count", "severity", "node_id", "label", "resolved_by", "edge_id", "new",
            "affected_routes", "route_id", "target", "length_m", "eta_min", "uses_unknown", "breach_required",
            "approval_id", "status", "message_id", "count"]
    parts = [f"{k}={res[k]}" for k in keys if k in res and res[k] not in (None, False, [])]
    if "ranked" in res:
        parts.append("top: " + ", ".join(f"#{r['rank']} {r['kind']}@{r['node']} ({r['score']})" for r in res["ranked"][:4]))
    if "forecasts" in res:
        parts.append(f"{len(res['forecasts'])} forecasts")
    return "✓ " + " ".join(parts)[:220]


class Run:
    def __init__(self, agent: str):
        self.agent = agent
        self.calls: list[dict] = []
        self.results: list[tuple[str, dict]] = []  # raw results (not logged)

    def tool(self, name: str, **args) -> dict:
        if name == "propose_action":
            args.setdefault("agent", self.agent)
        res = tools.call(name, args)
        shown = {k: v for k, v in args.items() if k != "agent"}
        self.calls.append({"tool": name, "args": shown, "result_summary": _summ(res)})
        self.results.append((name, res))
        return res

    def last(self, name: str) -> dict | None:
        return next((r for n, r in reversed(self.results) if n == name and r.get("ok")), None)

    def called(self, name: str) -> bool:
        return any(c["tool"] == name for c in self.calls)


def _log(agent: str, input_summary: str, run: Run, output: str, mode: str) -> None:
    db.conn().execute("INSERT INTO agent_log(agent,input_summary,tool_calls_json,output_summary,ts,mode) VALUES(?,?,?,?,?,?)",
                      (agent, input_summary[:300], json.dumps(run.calls), output[:600], tools.now(), mode))
    db.conn().commit()
    state.broadcast()


def log_event(agent: str, input_summary: str, output: str, calls: list | None = None) -> None:
    r = Run(agent)
    r.calls = calls or []
    _log(agent, input_summary, r, output, "system")


def _clean(text: str | None) -> str:
    t = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S).strip()
    return t[:600] or "(no summary)"


async def _llm_loop(run: Run, system: str, user: str, tool_names: list[str], max_steps: int = 6,
                    max_tokens: int = 900, raw: bool = False) -> str:
    c = _cfg()
    sys_prompt = ("detailed thinking off\n" if "nemotron" in c["model"].lower() else "") + system
    messages: list[dict] = [{"role": "system", "content": sys_prompt}, {"role": "user", "content": user}]
    spec = tools.openai_tools(tool_names) if tool_names else None
    for _ in range(max_steps):
        kw = dict(model=c["model"], messages=messages, temperature=0.2, max_tokens=max_tokens)
        if spec:
            kw.update(tools=spec, tool_choice="auto")
        if re.search(r"nemotron-3", c["model"].lower()):
            # Nemotron 3.x toggles reasoning via the chat template; keep it off so agent steps stay fast
            kw["extra_body"] = {"chat_template_kwargs": {"enable_thinking": False}}
        resp = await client().chat.completions.create(**kw)
        msg = resp.choices[0].message
        if not msg.tool_calls:
            if raw:  # structured output (JSON): strip reasoning tags only, never truncate
                return re.sub(r"<think>.*?</think>", "", msg.content or "", flags=re.S).strip()
            return _clean(msg.content)
        messages.append({"role": "assistant", "content": msg.content or "",
                         "tool_calls": [{"id": tc.id, "type": "function",
                                         "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                                        for tc in msg.tool_calls]})
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            res = run.tool(name, **args) if name in tool_names else {"ok": False, "reason": f"tool {name} not allowed"}
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(res, default=str)[:3500]})
    return "(step limit reached)"


async def run_agent(agent: str, input_summary: str, *, system: str, user: str, tool_names: list[str],
                    mock: Callable[[Run], str], validate: Callable[[Run], bool] | None = None,
                    pre: Callable[[Run], None] | None = None) -> tuple[str, Run]:
    run = Run(agent)
    if pre:
        pre(run)
    mode, why = configured_mode()
    out = None
    if mode == "live":
        n_pre = len(run.calls)
        try:
            out = await asyncio.wait_for(_llm_loop(run, system, user, tool_names), timeout=_cfg()["timeout"])
            if validate and not validate(run):
                raise ValueError("model skipped a required tool call")
            db.set_meta("agent_mode", {"mode": "live", "reason": _cfg()["model"]})
        except Exception as e:  # noqa: BLE001 — any failure → deterministic fallback
            why = f"fallback: {type(e).__name__}"
            db.set_meta("agent_mode", {"mode": "mock", "reason": why})
            run.calls.append({"tool": "—", "args": {}, "result_summary": f"⚠ live call failed ({type(e).__name__}: {str(e)[:80]}) → MOCK"})
            out, mode = None, "mock"
            del n_pre
    if out is None:
        out = mock(run)
        mode = "mock"
    _log(agent, input_summary, run, out, mode)
    return out, run


# ================================================================ 1. REPORT AGENT
CRIT = ("pinned", "can't move", "cannot move", "unconscious", "no movement", "not breathing", "crushed", "fall alert", "bleeding heavily",
        "bleeding profusely", "bleeding out", "heavy bleeding", "severe bleeding", "dying", "can't breathe", "cant breathe",
        "cannot breathe", "unresponsive", "not responding", "heart attack", "chest pain", "losing consciousness", "passing out")
# Deterministic safety rules applied AFTER the model (live or mock): life-threat language is never down-graded,
# and explicit all-clear messages never become incidents.
ALL_CLEAR = ("all good", "all clear", "i'm fine", "im fine", "i am fine", "i'm ok", "im ok", "i am ok", "we're ok", "we are ok",
             "we're fine", "we are fine", "false alarm", "never mind", "nevermind", "no fire", "no smoke", "no gas",
             "everything is fine", "i'm safe", "im safe", "i am safe", "we are safe", "we're safe", "no danger")
NOT_CLEAR = ("trapped", "stuck", "bleed", "hurt", "injur", "help", "pinned", "dying", "blocked", "debris", "can't", "cant",
             "cannot", "smell", "pain", "fall", "but ")


def is_all_clear(text: str) -> bool:
    t = text.lower().replace("’", "'")
    return any(w in t for w in ALL_CLEAR) and not any(w in t for w in NOT_CLEAR) and not any(w in t for w in CRIT)


def life_threat(text: str) -> str | None:
    t = text.lower().replace("’", "'")
    return next((w for w in CRIT if w in t), None)
URG = ("trapped", "stuck", "locked inside", "won't open", "bleeding", "gas", "fire", "smoke", "injured", "hurt", "broken leg", "near miss")
BLOCK = ("blocked", "debris", "impassable", "can't get through", "cannot get through", "caved", "rubble")
HAZ = ("gas", "fire", "smoke", "leak", "traffic lights", "signals", "sparks", "flood", "power", "generator", "sos only", "can't get through to 911")


def classify(text: str, hint: str | None) -> tuple[str, str]:
    t = text.lower().replace("’", "'")
    comms = any(w in t for w in ("911", "sos only", "no signal", "no service"))
    if hint == "blocked_route" or (any(w in t for w in BLOCK) and not comms):
        kind = "blocked_route"
    elif hint == "hazard" or (any(w in t for w in HAZ) and not any(w in t for w in ("pinned", "locked inside", "trapped"))):
        kind = "hazard"
    elif any(w in t for w in ("trapped", "pinned", "locked inside", "stuck", "won't open")):
        kind = "trapped"
    elif any(w in t for w in ("cut", "injur", "bleed", "hurt", "fall alert", "heart rate", "first aid")):
        kind = "medical"
    else:
        kind = "distress"
    sev = "critical" if any(w in t for w in CRIT) else "urgent" if any(w in t for w in URG) else "requested"
    if kind == "blocked_route":
        sev = "requested"
    if any(w in t for w in ("small cut", "minor", "mostly ok", "first aid kit")) and sev != "critical":
        sev = "requested"
    return kind, sev


REPORT_SYS = """You are the HoloSafe REPORT AGENT in an emergency coordination system.
Ingest one raw report. Steps (use tools, never guess ids):
1. Call spatial_lookup with the device node_id AND the report text, to resolve the exact location (e.g. 'room 305').
2. If the report says a route/stair/corridor is blocked: call update_edge_status(status='reported_blocked', node_id=<resolved node>), then create_incident(kind='blocked_route', severity='requested').
   Otherwise call create_incident with the resolved node_id, a kind (distress|trapped|medical|hazard), and severity:
   critical = life threat now (pinned, unconscious, no movement, heavy/profuse bleeding, "dying", can't breathe);
   urgent = trapped/minor bleeding/gas/fire; requested = minor/info. When in doubt between two levels, pick the HIGHER one.
   Set confidence 0-1 from source reliability and specificity. Pass person_id if given.
3. Reply with ONE short sentence: classification, location, confidence. No markdown."""


async def report_agent(rep: dict) -> dict:
    """rep: {text, node_id, source, kind?, person_id?, confidence?}"""
    hint = rep.get("kind")
    base_conf = rep.get("confidence") or {"beacon": 0.6, "responder": 0.9, "third_party": 0.8}.get(rep.get("source"), 0.6)
    if len(rep["text"].split()) < 5:
        base_conf -= 0.1
    result: dict = {}
    if is_all_clear(rep["text"]):
        # status update, not an emergency: log it against the location, create nothing
        run = Run("Report Agent")
        loc = run.tool("spatial_lookup", node_id=rep["node_id"], text=rep["text"])
        _log("Report Agent", f"[{rep.get('source')}] “{rep['text'][:90]}”", run,
             f"ALL-CLEAR from {loc.get('label', rep['node_id'])}: noted as a status update, no incident created.", "system")
        return {"all_clear": True}

    def mock(run: Run) -> str:
        loc = run.tool("spatial_lookup", node_id=rep["node_id"], text=rep["text"])
        nid = loc.get("node_id", rep["node_id"])
        kind, sev = classify(rep["text"], hint)
        if kind == "blocked_route":
            e = run.tool("update_edge_status", status="reported_blocked", node_id=nid, source=rep.get("source", "civilian"),
                         confidence=round(base_conf, 2), note=rep["text"][:80])
            result["edge"] = e
        inc = run.tool("create_incident", node_id=nid, severity=sev, kind=kind, description=rep["text"],
                       source=rep.get("source", "civilian"), confidence=round(base_conf, 2), person_id=rep.get("person_id"))
        result["incident"] = inc
        merged = f" — merged into {inc.get('incident_id')} ({inc.get('report_count')} reports)" if inc.get("merged") else ""
        return f"{kind.upper()} / {sev} at {loc.get('label', nid)} [{loc.get('resolved_by', '?')}], conf {base_conf:.2f}{merged}"

    user = json.dumps({"report_text": rep["text"], "device_node_id": rep["node_id"], "source": rep.get("source"),
                       "form_category": hint, "person_id": rep.get("person_id"), "source_confidence": round(base_conf, 2)})
    out, run = await run_agent("Report Agent", f"[{rep.get('source')}] “{rep['text'][:90]}”", system=REPORT_SYS, user=user,
                               tool_names=["spatial_lookup", "create_incident", "update_edge_status"], mock=mock,
                               validate=lambda r: r.called("create_incident") or r.called("update_edge_status"))
    # live path: recover what the model did from the raw tool results
    result.setdefault("incident", run.last("create_incident") or {})
    if run.last("update_edge_status"):
        result.setdefault("edge", run.last("update_edge_status"))
    inc = result["incident"]
    hit = life_threat(rep["text"])
    if hit and inc.get("incident_id") and inc.get("severity") != "critical":
        db.update("incidents", inc["incident_id"], severity="critical")
        log_event("Report Agent", f"SAFETY FLOOR · {inc['incident_id']}",
                  f"Life-threat language (“{hit}”) → severity raised {inc.get('severity')} → CRITICAL. "
                  "Deterministic rule: a model may never rank this below critical.")
        inc["severity"] = "critical"
    return result


# ================================================================ 2. SITUATION AGENT
SITUATION_SYS = """You are the HoloSafe SITUATION AGENT. Maintain the world picture and prioritise.
Call rank_incidents (deterministic scoring: severity, isolation, vulnerability, time sensitivity, accessibility, confidence —
report VOLUME is ignored on purpose). Then explain the top priorities in 2-3 short sentences for the incident commander:
who is #1 and why, call out any isolated or vulnerable person, and note people flagged 'needs assessment' (unknown mobility —
never assume they can self-evacuate). No markdown."""


def _flag_vulnerable(run: Run) -> None:
    cfg = scenario.current_cfg()
    if not cfg:
        return
    ev = scenario.evacuate_buildings(cfg)
    for p in db.q("SELECT p.*, n.building_id, n.floor FROM people p JOIN nodes n ON n.id=p.node_id"):
        in_area = ev is None or p["building_id"] in ev
        if not in_area:
            continue
        if p["mobility"] == "unknown" and not p["needs_assessment"]:
            db.update("people", p["id"], needs_assessment=1)
            run.tool("create_incident", node_id=p["node_id"], severity="requested", kind="needs_assessment",
                     description=f"{p['name']}: mobility unknown — welfare check before routing", source="third_party",
                     confidence=p["location_confidence"], person_id=p["id"])
        elif p["mobility"] == "needs_assist" and p["status"] == "ok" and (p["floor"] or 1) > 1:
            run.tool("create_incident", node_id=p["node_id"], severity="urgent" if (p["floor"] or 1) >= 3 else "requested",
                     kind="assisted_evac", description=f"{p['name']}: needs assisted evacuation from floor {p['floor']}",
                     source="third_party", confidence=0.9, person_id=p["id"])
    # civilian-reported blockages: propose promotion to VERIFIED (human decides)
    decided = {json.loads(a["payload_json"]).get("edge_id") for a in db.q("SELECT payload_json FROM approvals WHERE action='verify_blocked'")}
    for e in db.q("SELECT * FROM edges WHERE status='reported_blocked'"):
        if e["id"] in decided:
            continue
        run.tool("propose_action", action="verify_blocked", title=f"Verify blocked: {tools.place(e['a'])} ↔ {tools.place(e['b']).split(' · ')[-1]}",
                 payload={"edge_id": e["id"]},
                 rationale=f"Reported by {e['status_source']} (conf {e['status_confidence']}). Civilians already routed around it; "
                           "verifying also removes it from responder access routes.")
    if cfg.get("shelters_unverified"):
        asked = {json.loads(a["payload_json"]).get("resource_id") for a in db.q(
            "SELECT payload_json FROM approvals WHERE action='declare_safe' AND status='pending'")}
        for r in db.q("SELECT * FROM resources WHERE kind='shelter' AND status='unverified'"):
            if r["id"] in asked:
                continue
            run.tool("propose_action", action="declare_safe", title=f"Declare {r['name']} safe",
                     payload={"resource_id": r["id"], "node_id": r["node_id"]},
                     rationale="Shelter outside damage footprint; drone pass shows no structural hazards. Until approved it stays UNVERIFIED.")


async def situation_agent(trigger: str) -> dict:
    def mock(run: Run) -> str:
        rk = run.tool("rank_incidents")
        ranked = rk.get("ranked", [])
        if not ranked:
            return "No open incidents."
        top = ranked[0]
        iso = next((r for r in ranked if "isolated" in r["why"] and r["severity"] == "critical"), None)
        na = sum(1 for r in ranked if r["kind"] == "needs_assessment")
        s = f"#1 {top['kind']} at {top['place']} (score {top['score']}: {top['why']})."
        if iso and iso is not top:
            s += f" Isolated critical {iso['person_id'] or iso['node']} ({iso['place']}) ranked #{iso['rank']} on a single low-confidence report — no one nearby to report."
        vol = next((r for r in ranked if "volume ignored" in r["why"]), None)
        if vol:
            s += f" {vol['kind']} at {vol['place']} has {vol['why'].split(' reports')[0].split('· ')[-1]} reports but ranks #{vol['rank']} (minor)."
        if na:
            s += f" {na} people flagged NEEDS ASSESSMENT (mobility unknown) — not routed independently."
        return s

    def user_msg() -> str:
        return json.dumps({"trigger": trigger, "hazard": (db.get_meta("scenario") or {}).get("name")})

    out, run = await run_agent("Situation Agent", trigger, system=SITUATION_SYS, user=user_msg(),
                               tool_names=["rank_incidents"], mock=mock, pre=_flag_vulnerable,
                               validate=lambda r: r.called("rank_incidents"))
    return {"summary": out}


# ================================================================ 3. RESOURCE AGENT (Pathway B)
RESOURCE_SYS = """You are the HoloSafe RESOURCE AGENT (Pathway B: rescue). Match available responders to the highest-ranked
trapped/injured/critical incidents. For each match: call route(mode='responder', subject_id=<responder id>, to_kind='node',
to_node=<incident node>) and then propose_action(action='dispatch_responder', title, payload={responder_id, incident_id, route_id},
rationale) — dispatches need human approval. Prefer kind matches: search_rescue→trapped, ems→medical/assisted_evac, fire_rescue→hazard.
Use each responder at most once. Reply with one sentence summarising proposals. No markdown."""

KIND_PREF = {"trapped": "search_rescue", "medical": "ems", "distress": "ems", "assisted_evac": "ems", "hazard": "fire_rescue"}


def _rescue_candidates() -> list[dict]:
    pending_inc = {json.loads(a["payload_json"]).get("incident_id") for a in db.q(
        "SELECT payload_json FROM approvals WHERE action='dispatch_responder' AND status IN ('pending','approved')")}
    return [i for i in db.q("SELECT * FROM incidents WHERE severity IN ('critical','urgent') AND acknowledged=0 "
                            "AND kind IN ('trapped','medical','distress','hazard','assisted_evac') ORDER BY rank")
            if i["id"] not in pending_inc]


def _free_responders() -> list[dict]:
    busy = {json.loads(a["payload_json"]).get("responder_id") for a in db.q(
        "SELECT payload_json FROM approvals WHERE action='dispatch_responder' AND status='pending'")}
    return [r for r in db.q("SELECT * FROM responders WHERE status='available'") if r["id"] not in busy]


async def resource_agent(trigger: str) -> dict:
    cands, free = _rescue_candidates(), _free_responders()

    def mock(run: Run) -> str:
        avail = list(free)
        made = []
        for inc in cands:
            if not avail:
                break
            best, best_cost = None, 1e9
            for r in avail:
                rr = routing.route(r["node_id"], "node", "responder", to_node=inc["node_id"])
                if not rr["ok"]:
                    continue
                cost = rr["length_m"] * (1.0 if KIND_PREF.get(inc["kind"]) == r["kind"] else 1.6)
                if cost < best_cost:
                    best, best_cost = r, cost
            if not best:
                continue
            rt = run.tool("route", mode="responder", subject_id=best["id"], to_kind="node", to_node=inc["node_id"],
                          note=f"access to {inc['id']}")
            if not rt.get("ok"):
                continue
            flags = []
            if rt.get("breach_required"):
                flags.append("forced entry required (verified blockage on route)")
            if rt.get("uses_unknown"):
                flags.append("passes UNVERIFIED segment — proceed with caution")
            run.tool("propose_action", action="dispatch_responder",
                     title=f"Dispatch {best['name']} → {tools.place(inc['node_id'])} (#{inc['rank']} {inc['kind'].replace('_', ' ')})",
                     payload={"responder_id": best["id"], "incident_id": inc["id"], "route_id": rt.get("route_id")},
                     rationale=f"{best['kind'].replace('_', ' ')} unit, {rt['length_m']} m / ~{rt['eta_min']} min. " + "; ".join(flags))
            avail.remove(best)
            made.append(f"{best['name']}→#{inc['rank']}")
        if not made:
            return "No new dispatches: " + ("all responders committed." if not avail else "no unassigned critical/urgent incidents.")
        return f"Proposed {len(made)} dispatch(es) for approval: " + ", ".join(made) + "."

    user = json.dumps({"incidents": [{"incident_id": i["id"], "rank": i["rank"], "kind": i["kind"], "severity": i["severity"],
                                      "node": i["node_id"], "why": i["rank_reason"]} for i in cands[:6]],
                       "available_responders": [{"id": r["id"], "name": r["name"], "kind": r["kind"], "at": r["node_id"]} for r in free]})
    if not cands or not free:
        return {"summary": "skipped"}
    out, _ = await run_agent("Resource Agent", trigger, system=RESOURCE_SYS, user=user,
                             tool_names=["route", "propose_action"], mock=mock,
                             validate=lambda r: r.called("propose_action"))
    return {"summary": out}


# ================================================================ 4. COMMS AGENT (Pathway A)
COMMS_SYS = """You are the HoloSafe COMMS AGENT (Pathway A: evacuation). Routes were already computed by the route tool
(civilian mode: blocked edges excluded, unknown edges avoided, responder corridor on Central Ave avoided).
Write ONE broadcast with notify (no person_id): what happened, what to do, keep off Central Ave. If any route changed, say which
segment is blocked and to follow the updated route. Then notify each person in 'needs_extra_message' individually (assisted or
needs-assessment). Keep messages under 160 characters, calm, imperative. Finish with one sentence summary. No markdown."""


def _route_invalid(path: list[str], bad: set[frozenset]) -> bool:
    return any(frozenset((a, b)) in bad for a, b in zip(path, path[1:]))


async def comms_agent(trigger: str, initial: bool = False) -> dict:
    cfg = scenario.current_cfg()
    if not cfg:
        return {}
    ev = scenario.evacuate_buildings(cfg)
    routed, rerouted, failed, sheltered = [], [], [], []

    def pre(run: Run) -> None:
        bad = {frozenset((e["a"], e["b"])) for e in db.q("SELECT a,b FROM edges WHERE status IN ('reported_blocked','verified_blocked')")}
        active = {r["subject_id"]: r for r in db.q("SELECT * FROM routes WHERE status='active' AND subject_type='person'")}
        for p in db.q("SELECT p.*, n.building_id FROM people p JOIN nodes n ON n.id=p.node_id"):
            in_area = ev is None or p["building_id"] in ev or (p["building_id"] is None and ev is None)
            if p["status"] in ("trapped", "injured", "rescued", "safe") or p["mobility"] == "unknown":
                continue
            if not in_area:
                if initial and p["status"] == "ok":
                    db.update("people", p["id"], status="sheltering")
                    sheltered.append(p["id"])
                continue
            cur = active.get(p["id"])
            if cur and not _route_invalid(json.loads(cur["path_json"]), bad):
                continue
            if not cur and not initial and p["status"] != "ok":
                continue
            res = run.tool("route", mode="civilian", subject_id=p["id"], to_kind="safe_zone",
                           note="re-route: segment blocked" if cur else "evacuation")
            if res.get("ok"):
                db.update("people", p["id"], status="evacuating")
                (rerouted if cur else routed).append((p, res))
                txt = (f"ROUTE CHANGED — blocked segment ahead. New route: {res['describe']}" if cur
                       else f"EVACUATE: {res['describe']} ({res['length_m']} m, ~{res['eta_min']} min)")
                run.tool("notify", person_id=p["id"], text=txt)
            else:
                failed.append(p)
                run.tool("create_incident", node_id=p["node_id"], severity="urgent", kind="trapped",
                         description=f"{p['name']}: no passable civilian route ({res.get('reason')})", source="third_party",
                         confidence=0.7, person_id=p["id"])

    def mock(run: Run) -> str:
        if initial:
            areas = "all buildings" if ev is None else ", ".join(sorted(ev))
            msg = (f"{cfg['name']}: evacuate {areas} now via your HoloSafe route. Keep Central Ave clear for responders."
                   if routed else f"{cfg['name']}: shelter in place unless told otherwise.")
            if sheltered and routed:
                msg += " Everyone else: shelter in place."
            run.tool("notify", text=msg)
        if rerouted and not initial:
            run.tool("notify", text=f"Route update: {len(rerouted)} people re-routed around a reported blockage. Follow your updated route.")
        parts = []
        if routed:
            parts.append(f"{len(routed)} evacuation routes issued")
        if rerouted:
            parts.append(f"{len(rerouted)} re-routed")
        if sheltered:
            parts.append(f"{len(sheltered)} told to shelter in place")
        if failed:
            parts.append(f"{len(failed)} with no passable route → rescue queue")
        na = db.q1("SELECT COUNT(*) n FROM people WHERE needs_assessment=1")["n"]
        if na:
            parts.append(f"{na} held for assessment (mobility unknown)")
        q = " (offline: messages QUEUED)" if db.get_meta("offline", False) else ""
        return ("; ".join(parts) or "No route changes needed") + q + "."

    def user() -> str:
        return json.dumps({"hazard": cfg["name"], "initial_broadcast": initial,
                           "routes_issued": [{"person": p["id"], "route": r["describe"], "m": r["length_m"]} for p, r in routed][:12],
                           "routes_changed": [{"person": p["id"], "route": r["describe"]} for p, r in rerouted],
                           "no_route": [p["id"] for p in failed],
                           "needs_extra_message": [p["id"] for p, _ in routed if p["mobility"] == "needs_assist"]})

    # Run the deterministic routing step first so a no-op event doesn't cost an LLM call.
    tmp = Run("Comms Agent")
    pre(tmp)
    if not initial and not rerouted and not routed and not failed:
        return {"summary": "no changes"}
    out, _ = await run_agent("Comms Agent", trigger, system=COMMS_SYS, user=user(), tool_names=["notify"], mock=mock,
                             pre=lambda r: r.calls.extend(tmp.calls), validate=lambda r: r.called("notify"))
    return {"summary": out, "rerouted": len(rerouted)}


# ================================================================ 5. SIMULATION AGENT
SIM_SYS = """You are the HoloSafe SIMULATION AGENT. You receive forecasts produced by the deterministic cascade_forecast tool.
Do NOT add, remove or change forecasts. For EACH forecast id write: a plain-language explanation (<=25 words, for an incident
commander), one concrete precaution (imperative, <=20 words) and deadline_hours (a number: when the precaution must be done,
before the forecast horizon). Output valid JSON only. No explanation. No markdown.
Schema: {"annotations":[{"id":"...","explanation":"...","precaution":"...","deadline_hours":1.5}]}"""


def _target_name(f: dict) -> str:
    if f["target_kind"] == "infra":
        i = db.q1("SELECT name FROM infra WHERE id=?", (f["target_id"],))
        return i["name"] if i else f["target_id"]
    if f["target_kind"] == "building":
        b = db.q1("SELECT name FROM buildings WHERE id=?", (f["target_id"],))
        return b["name"] if b else f["target_id"]
    if f["target_kind"] == "node":
        return tools.place(f["target_id"])
    return "epicentre zone"


def _mock_annotation(f: dict, cfg: dict, eta: float | None) -> dict:
    tpl = (cfg.get("precautions") or {}).get(f["kind"], {})
    vec = (cfg.get("attack_vector") or {}).get("network", "control")
    name = _target_name(f)
    dl = tpl.get("deadline_h")
    if dl is None:
        dl = round(max(0.5, (eta if eta is not None else f["horizon_hours"]) * 0.75), 1)
    pct = f"{f['confidence']:.0%}"
    expl = {
        "aftershock": f"{pct} chance of a damaging aftershock near the epicentre within {f['horizon_hours']:g}h; risk falls over time.",
        "weakened_building": f"{name} took heavy shaking; {pct} chance of further structural failure if an aftershock hits.",
        "fire": f"Leaking gas at Main St can ignite; fire could reach {name} by +{f['horizon_hours']:g}h ({pct}).",
        "power_loss": f"{name} goes dark around T+{eta if eta is not None else f['horizon_hours']:g}h when its backup power runs out ({pct}).",
        "comms_loss": f"{name} battery backup ends ~T+{eta if eta is not None else f['horizon_hours']:g}h; phones in its cell lose service ({pct}).",
        "water_loss": f"{name} stops pumping without grid power; water pressure drops for hospital and hydrants ({pct}).",
        "traffic_loss": f"{name} go dark; uncontrolled intersections slow ambulances ({pct}).",
        "compromise": f"{name} shares the attacked system; attackers can likely move to it next ({pct}).",
    }.get(f["kind"], f["reason"])
    return {"explanation": expl, "precaution": tpl.get("text", "Monitor.").format(target=name, vector=vec), "deadline_hours": dl}


def _parse_json(text: str) -> dict:
    t = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", t, flags=re.S)
    return json.loads(m.group(0) if m else t)


async def simulation_agent(trigger: str) -> dict:
    cfg = scenario.current_cfg()
    if not cfg:
        return {}
    run = Run("Simulation Agent")
    res = run.tool("cascade_forecast", hazard=cfg["id"], horizons=[1, 6, 24])
    fcs = [f for f in res.get("forecasts", []) if f["status"] == "predicted"]
    eta = {f["id"]: f.get("eta_h") for f in res.get("forecasts", [])}
    rows = {f["id"]: f for f in db.q("SELECT * FROM forecasts WHERE status='predicted'")}
    ann: dict[str, dict] = {}
    mode, why = configured_mode()
    if mode == "live" and fcs:
        try:
            run.calls.append({"tool": "nemotron.reason", "args": {"forecasts": len(fcs)}, "result_summary": "annotating…"})
            text = await asyncio.wait_for(_llm_loop(run, SIM_SYS, json.dumps({"hazard": cfg["name"], "forecasts": fcs}), [],
                                                    max_tokens=4000, raw=True),
                                          timeout=_cfg()["timeout"])
            data = _parse_json(text)
            for a in data.get("annotations", []):
                if a.get("id") in rows and a.get("precaution"):
                    ann[a["id"]] = {"explanation": str(a.get("explanation", ""))[:200], "precaution": str(a["precaution"])[:160],
                                    "deadline_hours": float(a.get("deadline_hours") or rows[a["id"]]["horizon_hours"])}
            run.calls[-1]["result_summary"] = f"✓ {len(ann)}/{len(fcs)} forecasts annotated"
            db.set_meta("agent_mode", {"mode": "live", "reason": _cfg()["model"]})
        except Exception as e:  # noqa: BLE001
            db.set_meta("agent_mode", {"mode": "mock", "reason": f"fallback: {type(e).__name__}"})
            run.calls.append({"tool": "—", "args": {}, "result_summary": f"⚠ live call failed ({type(e).__name__}) → MOCK"})
            mode = "mock"
    else:
        mode = "mock"
    for fid, row in rows.items():
        a = ann.get(fid) or _mock_annotation(row, cfg, eta.get(fid))
        if fid not in ann and mode == "live":
            mode = "live+mock"
        db.update("forecasts", fid, explanation=a["explanation"], precaution=a["precaution"], deadline_hours=a["deadline_hours"])

    # operational precautions → human approval (grouped so one decision covers a whole chain)
    groups: dict[tuple, dict] = {}
    for fid, row in rows.items():
        tpl = (cfg.get("precautions") or {}).get(row["kind"], {})
        if not tpl.get("operational"):
            continue
        act = tpl["action"]
        if tpl.get("averts_kind"):
            key = (act, row["kind"])
        elif act == "restrict_entry":
            key = (act, row["target_id"])
        else:
            key = (act, row["target_id"])
        g = groups.setdefault(key, {"action": act, "rows": [], "target": row})
        g["rows"].append(row)
    for (act, _), g in groups.items():
        tgt = g["target"]
        ids = [r["id"] for r in g["rows"]]
        if act == "isolate_network":
            ids += [f for f, r in rows.items() if tgt["target_id"] in json.loads(r["chain_json"] or "[]") and f not in ids]
        if act == "restrict_entry":
            ids = []  # restricting entry protects people; it doesn't stop the building weakening
        first = min(g["rows"], key=lambda r: r["horizon_hours"])
        name = _target_name(tgt)
        a = ann.get(first["id"]) or _mock_annotation(first, cfg, eta.get(first["id"]))
        title = {"shut_gas_valve": "Shut gas main valve GAS-1 — prevents fire spread",
                 "fuel_resupply": f"Fuel resupply → {name} (before T+{a['deadline_hours']:g}h)",
                 "isolate_network": f"Isolate {name} from the attacked network",
                 "restrict_entry": f"Restrict re-entry: {name}"}.get(act, a["precaution"])
        payload = {"forecast_ids": sorted(set(ids))}
        if tgt["target_kind"] == "infra":
            payload["infra_id"] = tgt["target_id"]
        if tgt["target_kind"] == "building":
            payload["building_id"] = tgt["target_id"]
        run.tool("propose_action", action=act, title=title, payload=payload,
                 rationale=f"{a['precaution']} · deadline T+{a['deadline_hours']:g}h · {len(ids)} forecast(s) averted if done.")
    by_h = {h: sum(1 for r in rows.values() if r["horizon_hours"] == h) for h in (1, 6, 24)}
    out = (f"{len(rows)} predicted effects (+1h: {by_h[1]}, +6h: {by_h[6]}, +24h: {by_h[24]}); "
           f"{len(groups)} operational precaution(s) sent for approval. Predicted ≠ confirmed: shown as violet volumes.")
    _log("Simulation Agent", trigger, run, out, "live" if mode.startswith("live") else "mock")
    return {"summary": out}

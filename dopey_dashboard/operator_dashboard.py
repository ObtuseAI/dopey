"""DOPEY operator dashboard - localhost-only paper-research control panel.

One clean page: START / STOP the research supervisor, the open paper book,
closed positions and P&L, screener trade targets, the paper-trading record
and its progress toward the evidence bar, the readiness gate's 9 checks, and
system health (last ritual, supervisor journal, halts).

HARD BOUNDARIES:
- Binds 127.0.0.1 ONLY. No credentials, no external resources, no broker
  wiring. The page reads paper artifacts and nothing else.
- START spawns the resilient research supervisor (paper research). STOP
  terminates that process tree and clears ONLY a lock we know belongs to it.
  There is no order button and there never will be one here: execution stays
  sealed behind the action-readiness gate plus explicit human approval.

Usage:  .venv\\Scripts\\python -m dopey_dashboard.operator_dashboard
        then open http://127.0.0.1:8787
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts" / "dopey"
PYTHON_EXE = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
SUPERVISOR_LOCK_PATH = REPO_ROOT / "artifacts" / ".supervisor.lock"

HOST = "127.0.0.1"
PORT = 8787

LEDGER_PATH = ARTIFACTS / "forward_walk" / "forward_walk_ledger.json"
INTRADAY_PATH = ARTIFACTS / "intraday" / "intraday_decision_packet.json"
GATE_PATH = ARTIFACTS / "broker_readiness" / "action_readiness_gate.json"
SCREENER_SUMMARY_PATH = ARTIFACTS / "screener" / "screener_summary.json"
UNIVERSE_SUMMARY_PATH = ARTIFACTS / "universe" / "universe_summary.json"
SIGNAL_CALIBRATION_PATH = ARTIFACTS / "signal_calibration" / "signal_calibration_summary.json"
JOURNAL_PATH = ARTIFACTS / "research_supervisor" / "supervisor_run_journal.jsonl"
NIGHTLY_DIR = ARTIFACTS / "nightly"
MACRO_PATH = ARTIFACTS / "macro_context" / "macro_context_summary.json"
EQUITY_SWING_SUMMARY_PATH = ARTIFACTS / "equity_swing" / "equity_first_swing_summary.json"
CONTEXT_EVIDENCE_GATE_PATH = ARTIFACTS / "equity_swing" / "context_evidence_gate.json"

_STATE_LOCK = threading.Lock()
_CHILD: dict[str, object] = {"proc": None, "started_utc": ""}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_jsonl_tail(path: Path) -> dict:
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return json.loads(lines[-1]) if lines else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _position_pnl(position: dict) -> float | None:
    entry = position.get("entry_fill")
    mark = position.get("last_mark_bid")
    if isinstance(entry, (int, float)) and isinstance(mark, (int, float)):
        return round(float(mark) - float(entry), 4)
    return None


def _universe_line() -> dict:
    universe = _read_json(UNIVERSE_SUMMARY_PATH)
    counts = universe.get("tier_counts", {}) if isinstance(universe.get("tier_counts"), dict) else {}
    return {
        "active_size": universe.get("active_universe_size"),
        "core": counts.get("core"),
        "probation": counts.get("probation"),
        "candidates": counts.get("candidate"),
        "quarantined": counts.get("quarantined"),
        "staging_queue": universe.get("staging_queue", []),
        "retire_recommendations": len(universe.get("retire_recommendations", []) or []),
    }


def _calibration_line() -> dict:
    calibration = _read_json(SIGNAL_CALIBRATION_PATH)
    return {
        "settled": calibration.get("settled_total"),
        "overall_hit_rate": calibration.get("overall_hit_rate"),
        "contested_hit_rate": calibration.get("contested_hit_rate"),
        "semantics": calibration.get("semantics", ""),
    }


def _equity_swing_line() -> dict:
    summary = _read_json(EQUITY_SWING_SUMMARY_PATH)
    cross_asset = summary.get("cross_asset_context", {})
    series_quality = cross_asset.get("series_quality", {})
    news = summary.get("news_context", {})
    evidence = _read_json(CONTEXT_EVIDENCE_GATE_PATH)
    direction = summary.get("direction_authority", {})
    return {
        "engine_version": summary.get("engine_version", "not_run"),
        "as_of_date": summary.get("as_of_date", ""),
        "symbols_analyzed": summary.get("equity_symbol_count"),
        "complete_structures": summary.get("complete_structure_count"),
        "actionable_symbols": summary.get("actionable_symbols", []),
        "tracked_contract_symbols": summary.get("selected_contract_symbols", []),
        "technical_weight": direction.get("stock_technicals_weight"),
        "fundamental_weight": direction.get("stock_fundamentals_weight"),
        "options_weight": direction.get("options_data_weight"),
        "cross_asset_series": cross_asset.get("series_count"),
        "cross_asset_usable": series_quality.get("usable_count"),
        "cross_asset_blocked": series_quality.get("blocked_count"),
        "news_events": news.get("event_count"),
        "news_sources": news.get("source_count_staged"),
        "official_news_sources": news.get("official_source_count_staged"),
        "evidence_status": evidence.get("evidence_status", "not_run"),
        "snapshot_days": evidence.get("joint_snapshot_day_count"),
        "calendar_duration_gate_enabled": bool(evidence.get("calendar_duration_gate_enabled", False)),
        "snapshot_history_role": evidence.get("snapshot_history_role", ""),
        "resolved_decisions": evidence.get("context_outcome_ledger_count"),
        "resolved_decisions_required": evidence.get("minimum_resolved_decisions"),
        "promotion_allowed": bool(evidence.get("positive_context_promotion_allowed", False)),
        "reproducibility_hash": summary.get("reproducibility_hash", ""),
    }


def _run_state() -> dict:
    proc = _CHILD.get("proc")
    running = proc is not None and getattr(proc, "poll", lambda: 0)() is None
    return {
        "supervisor_running": bool(running),
        "supervisor_pid": getattr(proc, "pid", None) if running else None,
        "started_utc": _CHILD.get("started_utc", "") if running else "",
        "lock_present": SUPERVISOR_LOCK_PATH.exists(),
    }


def build_state() -> dict:
    ledger = _read_json(LEDGER_PATH)
    open_positions = ledger.get("open_positions", []) if isinstance(ledger, dict) else []
    closed_trades = ledger.get("closed_trades", []) if isinstance(ledger, dict) else []
    intraday = _read_json(INTRADAY_PATH)
    gate = _read_json(GATE_PATH)
    screener = _read_json(SCREENER_SUMMARY_PATH)
    journal = _read_jsonl_tail(JOURNAL_PATH)
    macro = _read_json(MACRO_PATH)

    open_rows = []
    unrealized = 0.0
    unrealized_known = 0
    for position in open_positions:
        pnl = _position_pnl(position)
        if pnl is not None:
            unrealized += pnl
            unrealized_known += 1
        open_rows.append({
            "position_id": position.get("position_id", ""),
            "symbol": position.get("symbol", ""),
            "strategy": position.get("candidate_strategy", ""),
            "option_type": position.get("option_type", ""),
            "strike": position.get("strike"),
            "expiry": position.get("expiry", ""),
            "entry_date": position.get("entry_date", ""),
            "entry_fill": position.get("entry_fill"),
            "last_mark_bid": position.get("last_mark_bid"),
            "unrealized_premium_units": pnl,
            "marking_sessions": position.get("marking_sessions"),
        })

    closed_rows = []
    realized = 0.0
    wins = 0
    for trade in closed_trades:
        pnl = trade.get("realized_pnl_premium_units")
        if not isinstance(pnl, (int, float)):
            entry = trade.get("entry_fill")
            exit_fill = trade.get("exit_fill", trade.get("last_mark_bid"))
            pnl = (float(exit_fill) - float(entry)) if isinstance(entry, (int, float)) and isinstance(exit_fill, (int, float)) else None
        if isinstance(pnl, (int, float)):
            realized += float(pnl)
            if pnl > 0:
                wins += 1
        closed_rows.append({
            "position_id": trade.get("position_id", ""),
            "symbol": trade.get("symbol", ""),
            "strategy": trade.get("candidate_strategy", ""),
            "entry_date": trade.get("entry_date", ""),
            "close_date": trade.get("close_date", trade.get("exit_date", "")),
            "close_reason": trade.get("close_reason", trade.get("exit_reason", "")),
            "realized_premium_units": round(float(pnl), 4) if isinstance(pnl, (int, float)) else None,
        })

    closed_count = len(closed_rows)
    required = int(gate.get("forward_closed_trades_required", 100) or 100)
    checks = gate.get("checks", {})
    check_rows = (
        [{"check": name, "passed": bool(value)} for name, value in sorted(checks.items())]
        if isinstance(checks, dict) else []
    )

    fundamentals = macro.get("fundamentals", {}) if isinstance(macro.get("fundamentals"), dict) else {}
    vol = macro.get("vol_term_structure", {}) if isinstance(macro.get("vol_term_structure"), dict) else {}

    return {
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "run": _run_state(),
        "paper_record": {
            "open_count": len(open_rows),
            "closed_count": closed_count,
            "wins": wins,
            "win_rate": round(wins / closed_count, 4) if closed_count else None,
            "realized_premium_units": round(realized, 4),
            "unrealized_premium_units": round(unrealized, 4),
            "unrealized_marked_positions": unrealized_known,
            "sample_required": required,
            "sample_progress_pct": round(100.0 * closed_count / required, 1) if required else 0.0,
            "last_entry_date": ledger.get("last_entry_date", ""),
            "last_marking_date": ledger.get("last_marking_date", ""),
        },
        "open_positions": open_rows,
        "closed_positions": closed_rows[-50:],
        "intraday": {
            "market_clock": intraday.get("market_clock", ""),
            "status": intraday.get("intraday_status", ""),
            "live_book_pnl_premium_units": intraday.get("live_book_pnl_premium_units"),
            "positions_needing_attention": intraday.get("positions_needing_attention", []),
        },
        "targets": {
            "generated_utc": screener.get("generated_at_utc", ""),
            "top_by_archetype": screener.get("top_targets_by_archetype", {}),
            "elite_archive": screener.get("elite_archive", {}),
            "semantics": "research flags for human review - not orders, not entries",
        },
        "readiness_gate": {
            "status": gate.get("readiness_status", "unknown"),
            "action_ready": bool(gate.get("action_ready", False)),
            "checks": check_rows,
            "missing_requirements": gate.get("missing_requirements", []),
            "evidence_eta": gate.get("evidence_eta", {}),
        },
        "universe": _universe_line(),
        "signal_calibration": _calibration_line(),
        "equity_swing": _equity_swing_line(),
        "system": {
            "last_supervisor_run_utc": journal.get("run_utc", ""),
            "supervisor_status": journal.get("supervisor_status", ""),
            "stages_green": journal.get("stages_green"),
            "stages_degraded": journal.get("stages_completed_degraded"),
            "stages_failed_absorbed": journal.get("stages_failed_absorbed"),
            "regressions_vs_previous_run": journal.get("regressions_vs_previous_run", []),
            "nightly_verdicts_present": NIGHTLY_DIR.exists(),
            "risk_free_rate_pct": macro.get("risk_free_rate_30d_pct"),
            "vix_term_state": vol.get("term_structure_state", ""),
            "fundamental_short_candidates": fundamentals.get("short_candidates_tradable_now", []),
        },
        "envelope": {
            "paper_only": True,
            "live_blocked": True,
            "orders_possible_from_this_page": False,
            "execution_seal": "blocked_until_gate_all_green_plus_explicit_human_approval",
        },
    }


def start_supervisor() -> dict:
    with _STATE_LOCK:
        state = _run_state()
        if state["supervisor_running"]:
            return {"started": False, "reason": "already_running", **state}
        proc = subprocess.Popen(
            [str(PYTHON_EXE), "-m", "dopey_autonomy.run_resilient_research_supervisor"],
            cwd=str(REPO_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _CHILD["proc"] = proc
        _CHILD["started_utc"] = datetime.now(timezone.utc).isoformat()
        return {"started": True, "pid": proc.pid, "note": "paper research supervisor launched; stages journal as they complete"}


def stop_supervisor() -> dict:
    with _STATE_LOCK:
        proc = _CHILD.get("proc")
        state = _run_state()
        if not state["supervisor_running"] or proc is None:
            return {"stopped": False, "reason": "not_running", **state}
        pid = proc.pid
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True)
        # Clear the supervisor lock ONLY if it belongs to the process we just
        # terminated - never someone else's run.
        try:
            lock = json.loads(SUPERVISOR_LOCK_PATH.read_text(encoding="utf-8"))
            if int(lock.get("pid", -1)) == pid:
                SUPERVISOR_LOCK_PATH.unlink(missing_ok=True)
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        _CHILD["proc"] = None
        return {"stopped": True, "pid": pid, "note": "process tree terminated; journal keeps whatever stages completed"}


PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><title>DOPEY - Equity Intelligence Console</title>
<style>
:root{--bg:#080d16;--panel:#101824;--panel2:#0c1420;--edge:#26364a;--ink:#edf6ff;--dim:#8fa3b8;--green:#4ee1a0;--red:#ff6473;--amber:#f0b44d;--accent:#4da3ff;--cyan:#50d7e8}
*{box-sizing:border-box;margin:0;padding:0}
body{background:radial-gradient(circle at 10% 0,#10233a 0,var(--bg) 34%);color:var(--ink);font:14px/1.45 "Segoe UI",system-ui,sans-serif;padding:20px;max-width:1400px;margin:0 auto}
h1{font-size:22px;letter-spacing:1.4px} h1 small{color:var(--dim);font-weight:400;font-size:12px;margin-left:10px;letter-spacing:.2px}
header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px;flex-wrap:wrap;gap:10px}
.controls{display:flex;gap:10px;align-items:center}
button{border:1px solid var(--edge);border-radius:8px;padding:10px 26px;font-size:15px;font-weight:600;cursor:pointer;color:#fff}
#btn-start{background:#1f6feb}#btn-start:hover{background:#2a7aff}
#btn-stop{background:#8b1d1d}#btn-stop:hover{background:#a52a2a}
button:disabled{opacity:.45;cursor:not-allowed}
.runchip{padding:6px 12px;border-radius:20px;border:1px solid var(--edge);font-size:12px}
.run-on{color:var(--green);border-color:var(--green)} .run-off{color:var(--dim)}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px}
.panel{background:linear-gradient(145deg,var(--panel),var(--panel2));border:1px solid var(--edge);border-radius:12px;padding:15px;overflow-x:auto;box-shadow:0 10px 30px rgba(0,0,0,.16)}
.panel h2{font-size:12px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);margin-bottom:10px}
.hero{grid-column:1/-1;display:grid;grid-template-columns:minmax(360px,1.4fr) minmax(330px,1fr);gap:18px;align-items:center;padding:20px;border-color:#285c7d;background:linear-gradient(120deg,#10233a,#0c1724 62%,#10251f)}
.hero h2{color:var(--cyan);font-size:11px}.hero-title{font-size:28px;font-weight:750;line-height:1.12;letter-spacing:-.4px;margin-bottom:9px}.hero-copy{color:#b8c8d8;max-width:760px}.hero-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.hero-stat{background:rgba(3,10,18,.42);border:1px solid var(--edge);border-radius:9px;padding:10px}.hero-stat .v{font-size:20px;font-weight:750;color:var(--cyan)}.hero-stat .l{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.7px}
.truthline{margin-top:12px;color:var(--amber);font-size:11px}.hash{font-family:Consolas,monospace;font-size:10px;color:var(--dim);word-break:break-all;margin-top:7px}
.kpis{display:flex;gap:18px;flex-wrap:wrap}
.kpi .v{font-size:22px;font-weight:700}.kpi .l{font-size:11px;color:var(--dim)}
.pos{color:var(--green)}.neg{color:var(--red)}.mut{color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th{color:var(--dim);text-align:left;font-weight:500;padding:4px 8px;border-bottom:1px solid var(--edge)}
td{padding:4px 8px;border-bottom:1px solid #21262d;font-variant-numeric:tabular-nums}
.pill{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;border:1px solid var(--edge)}
.ok{color:var(--green);border-color:#238636}.no{color:var(--red);border-color:#da3633}
.bar{height:8px;background:#21262d;border-radius:5px;overflow:hidden;margin-top:6px}
.bar>div{height:100%;background:linear-gradient(90deg,#1f6feb,#3fb950)}
footer{margin-top:16px;color:var(--dim);font-size:11.5px;border-top:1px solid var(--edge);padding-top:10px}
.tag{color:var(--amber)}
</style></head><body>
<header>
  <h1>DOPEY <small>equity-first market intelligence &middot; paper-only &middot; truth-gated</small></h1>
  <div class="controls">
    <span id="runchip" class="runchip run-off">stopped</span>
    <button id="btn-start" onclick="act('start')">&#9654; START</button>
    <button id="btn-stop" onclick="act('stop')">&#9632; STOP</button>
  </div>
</header>
<div class="grid">
  <div class="panel hero">
    <div>
      <h2>Equity-first swing intelligence v3</h2>
      <div class="hero-title">Structure finds the trade.<br>Evidence earns the edge.</div>
      <div class="hero-copy">Daily, weekly, and monthly support/resistance and trend-channel structure set direction. Fundamentals confirm the thesis. Cross-asset and geopolitical context can defend against risk. Options data only selects the strategically tracked strike and expiry.</div>
      <div class="truthline" id="swing-truth"></div>
      <div class="hash" id="swing-hash"></div>
    </div>
    <div class="hero-grid" id="swing-kpis"></div>
  </div>
  <div class="panel" style="grid-column:1/-1">
    <h2>Paper trading record</h2>
    <div class="kpis" id="kpis"></div>
    <div class="bar"><div id="progress" style="width:0%"></div></div>
    <div class="mut" id="progress-label" style="font-size:11px;margin-top:4px"></div>
  </div>
  <div class="panel" style="grid-column:1/-1"><h2>Active positions</h2><div id="open"></div></div>
  <div class="panel"><h2>Trade targets (research flags &mdash; not orders)</h2><div id="targets"></div></div>
  <div class="panel"><h2>Readiness gate</h2><div id="gate"></div></div>
  <div class="panel"><h2>Closed positions</h2><div id="closed"></div></div>
  <div class="panel"><h2>System</h2><div id="system"></div></div>
</div>
<footer id="foot"></footer>
<script>
function fmt(x,d){return (x===null||x===undefined)?'&mdash;':(typeof x==='number'?x.toFixed(d===undefined?2:d):x)}
function cls(x){return x>0?'pos':(x<0?'neg':'mut')}
function act(k){fetch('/api/'+k,{method:'POST'}).then(r=>r.json()).then(()=>setTimeout(refresh,400))}
function refresh(){fetch('/api/state').then(r=>r.json()).then(render).catch(()=>{})}
function render(s){
  const run=s.run||{};const chip=document.getElementById('runchip');
  chip.textContent=run.supervisor_running?('running pid '+run.supervisor_pid):'stopped';
  chip.className='runchip '+(run.supervisor_running?'run-on':'run-off');
  document.getElementById('btn-start').disabled=!!run.supervisor_running;
  document.getElementById('btn-stop').disabled=!run.supervisor_running;
  const swing=s.equity_swing||{};
  document.getElementById('swing-kpis').innerHTML=
    heroStat(fmt(swing.symbols_analyzed,0),'equities')+
    heroStat(fmt(swing.complete_structures,0),'MTF structures')+
    heroStat(fmt(swing.cross_asset_usable,0)+'/'+fmt(swing.cross_asset_series,0),'cross-asset usable')+
    heroStat(fmt(swing.news_events,0),'news events')+
    heroStat((swing.actionable_symbols||[]).join(', ')||'&mdash;','shadow setups')+
    heroStat((swing.tracked_contract_symbols||[]).join(', ')||'&mdash;','tracked contracts');
  document.getElementById('swing-truth').textContent=
    'Evidence gate: '+swing.evidence_status+' | '+fmt(swing.snapshot_days,0)+' observed joint snapshot days (duration gate removed) | '+fmt(swing.resolved_decisions,0)+'/'+fmt(swing.resolved_decisions_required,0)+' resolved decisions | promotion '+(swing.promotion_allowed?'enabled':'blocked');
  document.getElementById('swing-hash').textContent=swing.reproducibility_hash?('reproducibility '+swing.reproducibility_hash):'run the equity-first engine to populate this surface';
  const p=s.paper_record||{};
  document.getElementById('kpis').innerHTML=
    kpi(p.open_count,'open positions')+kpi(p.closed_count,'closed trades')+
    kpi(p.win_rate===null?'&mdash;':(100*p.win_rate).toFixed(1)+'%','win rate')+
    kpi('<span class="'+cls(p.realized_premium_units)+'">'+fmt(p.realized_premium_units)+'</span>','realized P&amp;L (premium u)')+
    kpi('<span class="'+cls(p.unrealized_premium_units)+'">'+fmt(p.unrealized_premium_units)+'</span>','unrealized P&amp;L (premium u)')+
    kpi(fmt(s.intraday&&s.intraday.live_book_pnl_premium_units),'intraday live book P&amp;L')+
    kpi(p.last_marking_date||'&mdash;','last mark');
  document.getElementById('progress').style.width=Math.min(100,p.sample_progress_pct||0)+'%';
  document.getElementById('progress-label').textContent='evidence sample: '+p.closed_count+' / '+p.sample_required+' closed trades ('+(p.sample_progress_pct||0)+'%) — the gate needs the full sample before anything is judged';
  const open=(s.open_positions||[]);
  document.getElementById('open').innerHTML=open.length?table(
    ['symbol','strategy','type','strike','expiry','entry','entry fill','last bid','unrlzd','sessions'],
    open.map(o=>[o.symbol,o.strategy,o.option_type,fmt(o.strike,2),o.expiry,o.entry_date,fmt(o.entry_fill),fmt(o.last_mark_bid),'<span class="'+cls(o.unrealized_premium_units)+'">'+fmt(o.unrealized_premium_units)+'</span>',fmt(o.marking_sessions,0)])):'<span class="mut">no open paper positions</span>';
  const closed=(s.closed_positions||[]);
  document.getElementById('closed').innerHTML=closed.length?table(
    ['symbol','strategy','entry','closed','reason','realized'],
    closed.map(c=>[c.symbol,c.strategy,c.entry_date,c.close_date,c.close_reason,'<span class="'+cls(c.realized_premium_units)+'">'+fmt(c.realized_premium_units)+'</span>'])):'<span class="mut">no closed trades yet — the record starts with the first time-stop / target / stop exit</span>';
  const t=(s.targets&&s.targets.top_by_archetype)||{};
  let th='';Object.keys(t).forEach(a=>{const rows=t[a]||[];if(rows.length){th+='<div style="margin-bottom:8px"><span class="tag">'+a+'</span> &rarr; '+rows.map(r=>r.symbol+' <span class="mut">'+fmt(r.screen_score,3)+'</span>').join(', ')+' <span class="mut">('+rows[0].executable_structure+')</span></div>'}});
  document.getElementById('targets').innerHTML=(th||'<span class="mut">no positive-score targets</span>')+'<div class="mut" style="font-size:11px;margin-top:6px">'+((s.targets&&s.targets.semantics)||'')+'</div>';
  const g=s.readiness_gate||{};
  document.getElementById('gate').innerHTML='<div style="margin-bottom:8px">status: <b>'+g.status+'</b></div>'+
    (g.checks||[]).map(c=>'<span class="pill '+(c.passed?'ok':'no')+'" style="margin:2px">'+c.check+'</span>').join(' ')+
    '<div class="mut" style="font-size:11px;margin-top:8px">missing: '+((g.missing_requirements||[]).join(', ')||'none')+'</div>';
  const y=s.system||{};const u=s.universe||{};const cal=s.signal_calibration||{};
  document.getElementById('system').innerHTML=table(['',''],[
    ['universe',(u.active_size?u.active_size+' active ('+u.core+' core + '+(u.probation||0)+' probation)':'&mdash;')+(u.candidates?' &middot; '+u.candidates+' candidates':'')+(u.quarantined?' &middot; '+u.quarantined+' quarantined':'')+((u.staging_queue||[]).length?' &middot; queued: '+u.staging_queue.join(', '):'')],
    ['signal calibration',cal.settled?(cal.settled.toLocaleString()+' phantoms settled &middot; '+(100*cal.overall_hit_rate).toFixed(1)+'% overall / '+(100*cal.contested_hit_rate).toFixed(1)+'% contested (not trade evidence)'):'&mdash;'],
    ['last supervisor run',y.last_supervisor_run_utc||'&mdash;'],
    ['supervisor status',y.supervisor_status||'&mdash;'],
    ['stages g / d / f',fmt(y.stages_green,0)+' / '+fmt(y.stages_degraded,0)+' / '+fmt(y.stages_failed_absorbed,0)],
    ['regressions vs prev',(y.regressions_vs_previous_run||[]).length?y.regressions_vs_previous_run.join(', '):'none'],
    ['risk-free (30d)',fmt(y.risk_free_rate_pct)+'%'],
    ['VIX term state',y.vix_term_state||'&mdash;'],
    ['fundamental short flags',(y.fundamental_short_candidates||[]).join(', ')||'none'],
    ['intraday',(s.intraday&&(s.intraday.market_clock||s.intraday.status))||'&mdash;']]);
  document.getElementById('foot').innerHTML='paper-only &middot; live-blocked &middot; no order can be placed from this page &middot; execution seal: '+(s.envelope&&s.envelope.execution_seal)+' &middot; refreshed '+new Date().toLocaleTimeString();
}
function kpi(v,l){return '<div class="kpi"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>'}
function heroStat(v,l){return '<div class="hero-stat"><div class="v">'+v+'</div><div class="l">'+l+'</div></div>'}
function table(h,rows){return '<table><tr>'+h.map(x=>'<th>'+x+'</th>').join('')+'</tr>'+rows.map(r=>'<tr>'+r.map(c=>'<td>'+(c===undefined||c===null?'&mdash;':c)+'</td>').join('')+'</tr>').join('')+'</table>'}
refresh();setInterval(refresh,15000);
</script></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - http.server protocol
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/state":
            self._send(200, json.dumps(build_state()).encode("utf-8"), "application/json")
        else:
            self._send(404, b'{"error":"not_found"}', "application/json")

    def do_POST(self) -> None:  # noqa: N802 - http.server protocol
        if self.path == "/api/start":
            self._send(200, json.dumps(start_supervisor()).encode("utf-8"), "application/json")
        elif self.path == "/api/stop":
            self._send(200, json.dumps(stop_supervisor()).encode("utf-8"), "application/json")
        else:
            self._send(404, b'{"error":"not_found"}', "application/json")

    def log_message(self, fmt: str, *args) -> None:  # quiet console
        return


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), _Handler)
    print(json.dumps({
        "dashboard": f"http://{HOST}:{PORT}",
        "binds": "127.0.0.1 only",
        "controls": "start/stop of the paper research supervisor",
        "orders_possible": False,
        "paper_only": True,
        "live_blocked": True,
    }, indent=2))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if _run_state()["supervisor_running"]:
            stop_supervisor()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

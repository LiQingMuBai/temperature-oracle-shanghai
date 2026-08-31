#!/usr/bin/env python3
"""Resolve archived contracts and run a point-in-time paper-trading backtest."""
import argparse
import csv
import datetime as dt
import json
import subprocess
from pathlib import Path

from polymarket_snapshot_db import connect

ROOT = Path(__file__).resolve().parent
DEFAULT_DB = ROOT / "work" / "polymarket_snapshots.sqlite3"


def fetch_event(slug):
    raw = subprocess.check_output([
        "curl", "-fsS", "--max-time", "30", "-A", "Mozilla/5.0 Codex-research",
        "https://gamma-api.polymarket.com/events/slug/" + slug], timeout=40)
    return json.loads(raw)


def winning_outcome(event):
    winners = []
    for market in event.get("markets", []):
        prices = market.get("outcomePrices", [])
        if isinstance(prices, str):
            prices = json.loads(prices)
        yes_price = float(prices[0]) if prices else 0
        if market.get("closed") and yes_price >= 0.99:
            winners.append(market["groupItemTitle"])
    return winners[0] if len(winners) == 1 else None


def update_resolutions(db_path):
    today = dt.datetime.now().astimezone().date().isoformat()
    with connect(db_path) as db:
        pending = db.execute("""SELECT DISTINCT r.slug,r.contract_date FROM runs r
            LEFT JOIN resolutions z ON z.slug=r.slug
            WHERE z.slug IS NULL AND r.contract_date < ? ORDER BY r.contract_date""", (today,)).fetchall()
        updated = []
        for slug, contract_date in pending:
            try:
                winner = winning_outcome(fetch_event(slug))
            except Exception:
                continue
            if winner:
                resolved_at = dt.datetime.now().astimezone().isoformat()
                db.execute("INSERT OR REPLACE INTO resolutions VALUES (?,?,?,?,?)",
                           (slug, contract_date, winner, resolved_at, "Polymarket Gamma outcomePrices"))
                updated.append({"slug": slug, "winning_outcome": winner})
        return updated


def build_report(db_path, starting_bankroll=10.0):
    with connect(db_path) as db:
        snapshot_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
        outcome_count = db.execute("SELECT COUNT(*) FROM outcomes").fetchone()[0]
        paper_trade_count = db.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0]
        open_paper_trades = db.execute("""SELECT COUNT(*) FROM paper_trades p
            LEFT JOIN resolutions z ON z.slug=p.slug WHERE z.slug IS NULL""").fetchone()[0]
        open_contracts = db.execute("""SELECT COUNT(DISTINCT r.slug) FROM runs r
            LEFT JOIN resolutions z ON z.slug=r.slug WHERE z.slug IS NULL""").fetchone()[0]
        rows = db.execute("""
          SELECT p.slug,p.contract_date,p.notified_at,p.outcomes_json,p.model_probability,
                 p.executable_cost,p.net_edge,p.shares_per_outcome,z.winning_outcome,
                 p.hours_to_close,COALESCE(p.lead_bucket,'unknown'),p.prediction_probability,p.market_weight
          FROM paper_trades p JOIN resolutions z ON z.slug=p.slug
          ORDER BY p.contract_date,p.notified_at
        """).fetchall()
        shadow_rows = db.execute("""SELECT s.strategy,s.lead_bucket,s.outcomes_json,s.stake_usd,
            s.shares,s.net_edge,z.winning_outcome FROM shadow_trades s
            JOIN resolutions z ON z.slug=s.slug ORDER BY s.entered_at""").fetchall()
    trades=[]; equity=starting_bankroll; peak=equity; max_drawdown=0.0
    for slug,date,captured,outcomes_json,prob,cost,edge,shares,winner,hours_to_close,lead_bucket,prediction_prob,market_weight in rows:
        outcomes=json.loads(outcomes_json); stake=cost*shares; hit=winner in outcomes
        payout=shares if hit else 0.0; pnl=payout-stake; equity+=pnl; peak=max(peak,equity)
        max_drawdown=max(max_drawdown,(peak-equity)/peak if peak else 0)
        trades.append({"contract_date":date,"slug":slug,"entry_at":captured,
            "outcomes":" + ".join(outcomes),"model_probability":prob,"entry_cost":cost,
            "net_edge":edge,"stake_usd":stake,"winning_outcome":winner,"hit":hit,
            "pnl_usd":pnl,"equity_usd":equity,"hours_to_close":hours_to_close,
            "lead_bucket":lead_bucket})
        trades[-1]["prediction_probability"]=prediction_prob
        trades[-1]["market_weight"]=market_weight
    wins=sum(t["hit"] for t in trades); total_pnl=sum(t["pnl_usd"] for t in trades)
    shadow_performance={}
    for strategy,layer,outcomes_json,stake,shares,edge,winner in shadow_rows:
        key=f"{strategy}:{layer}"
        row=shadow_performance.setdefault(key,{"strategy":strategy,"lead_bucket":layer,
            "trades":0,"wins":0,"pnl_usd":0.,"edge_sum":0.})
        hit=winner in json.loads(outcomes_json)
        row["trades"]+=1;row["wins"]+=int(hit)
        row["pnl_usd"]+=(shares if hit else 0)-stake;row["edge_sum"]+=edge
    for row in shadow_performance.values():
        row["hit_rate"]=row["wins"]/row["trades"]
        row["average_weather_edge"]=row.pop("edge_sum")/row["trades"]
    lead_time_performance={}
    for bucket in ("24h","12h","6h","3h","unknown"):
        group=[t for t in trades if t["lead_bucket"]==bucket]
        if group:
            lead_time_performance[bucket]={"trades":len(group),"wins":sum(t["hit"] for t in group),
                "hit_rate":sum(t["hit"] for t in group)/len(group),
                "pnl_usd":sum(t["pnl_usd"] for t in group),
                "average_edge":sum(t["net_edge"] for t in group)/len(group)}
    report={"generated_at":dt.datetime.now().astimezone().isoformat(),
        "method":"every successfully delivered formal Telegram bet alert is one simulated entry; fees excluded",
        "snapshot_runs":snapshot_count,"outcome_rows":outcome_count,"unresolved_contracts":open_contracts,
        "paper_trade_alerts": paper_trade_count,"open_paper_trades":open_paper_trades,
        "resolved_trades":len(trades),"wins":wins,
        "hit_rate":wins/len(trades) if trades else None,"starting_bankroll_usd":starting_bankroll,
        "ending_equity_usd":equity,"total_pnl_usd":total_pnl,
        "return_pct":total_pnl/starting_bankroll if starting_bankroll else None,
        "maximum_drawdown_pct":max_drawdown,"lead_time_performance":lead_time_performance,
        "shadow_strategy_performance":list(shadow_performance.values()),
        "trades":trades}
    return report


def write_report(report, output_json, output_csv):
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    fields=["contract_date","slug","entry_at","outcomes","model_probability","entry_cost",
            "net_edge","stake_usd","winning_outcome","hit","pnl_usd","equity_usd",
            "hours_to_close","lead_bucket"]
    fields += ["prediction_probability","market_weight"]
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(report["trades"])


def main():
    ap=argparse.ArgumentParser();ap.add_argument("command",choices=["update","report","all"])
    ap.add_argument("--db",type=Path,default=DEFAULT_DB);ap.add_argument("--bankroll",type=float,default=10)
    args=ap.parse_args()
    if args.command in ("update","all"):
        print(json.dumps({"resolutions_added":update_resolutions(args.db)},ensure_ascii=False))
    if args.command in ("report","all"):
        report=build_report(args.db,args.bankroll)
        write_report(report,ROOT/"outputs"/"polymarket_trade_backtest.json",
                     ROOT/"outputs"/"polymarket_trade_backtest_trades.csv")
        print(json.dumps({k:v for k,v in report.items() if k!="trades"},ensure_ascii=False,indent=2))


if __name__ == "__main__": main()

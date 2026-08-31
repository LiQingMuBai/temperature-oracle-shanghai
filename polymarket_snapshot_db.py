#!/usr/bin/env python3
"""SQLite persistence for point-in-time Polymarket/model snapshots."""
import json
import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY,
  captured_at TEXT NOT NULL,
  contract_date TEXT NOT NULL,
  slug TEXT NOT NULL,
  raw_weather_center_c REAL,
  weather_center_c REAL,
  weather_sigma_c REAL,
  model_forecasts_json TEXT NOT NULL,
  config_json TEXT NOT NULL,
  hours_to_close REAL,
  lead_bucket TEXT,
  UNIQUE(captured_at, slug)
);
CREATE INDEX IF NOT EXISTS idx_runs_slug_time ON runs(slug, captured_at);
CREATE TABLE IF NOT EXISTS outcomes (
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  outcome TEXT NOT NULL,
  weather_prob REAL NOT NULL,
  market_prob REAL,
  best_bid REAL,
  best_ask REAL,
  bid_size REAL,
  ask_size REAL,
  ask_levels_json TEXT NOT NULL,
  prediction_prob REAL,
  market_weight REAL,
  PRIMARY KEY(run_id, outcome)
);
CREATE TABLE IF NOT EXISTS candidates (
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  rank_no INTEGER NOT NULL,
  outcomes_json TEXT NOT NULL,
  legs_json TEXT NOT NULL,
  model_probability REAL NOT NULL,
  executable_cost REAL NOT NULL,
  net_edge REAL NOT NULL,
  qualifies INTEGER NOT NULL,
  contains_model_mode INTEGER NOT NULL,
  contains_market_mode INTEGER NOT NULL DEFAULT 0,
  prediction_probability REAL,
  market_weight REAL,
  model_support_count INTEGER NOT NULL,
  minimum_leg_price REAL NOT NULL,
  shares_per_outcome REAL NOT NULL,
  PRIMARY KEY(run_id, rank_no)
);
CREATE INDEX IF NOT EXISTS idx_candidates_qualified ON candidates(qualifies, run_id);
CREATE TABLE IF NOT EXISTS resolutions (
  slug TEXT PRIMARY KEY,
  contract_date TEXT NOT NULL,
  winning_outcome TEXT NOT NULL,
  resolved_at TEXT NOT NULL,
  source TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paper_trades (
  id INTEGER PRIMARY KEY,
  run_id INTEGER NOT NULL UNIQUE REFERENCES runs(id) ON DELETE RESTRICT,
  notified_at TEXT NOT NULL,
  slug TEXT NOT NULL,
  contract_date TEXT NOT NULL,
  outcomes_json TEXT NOT NULL,
  legs_json TEXT NOT NULL,
  model_probability REAL NOT NULL,
  executable_cost REAL NOT NULL,
  net_edge REAL NOT NULL,
  shares_per_outcome REAL NOT NULL,
  stake_usd REAL NOT NULL,
  bankroll_at_signal_usd REAL NOT NULL,
  hours_to_close REAL,
  lead_bucket TEXT
  ,prediction_probability REAL
  ,market_weight REAL
);
CREATE INDEX IF NOT EXISTS idx_paper_trades_slug ON paper_trades(slug, notified_at);
"""


def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=30)
    db.execute("PRAGMA foreign_keys=ON")
    db.executescript(SCHEMA)
    # Forward-only lightweight migrations for databases created by earlier releases.
    for table, columns in {
        "runs": [("hours_to_close", "REAL"), ("lead_bucket", "TEXT")],
        "paper_trades": [("hours_to_close", "REAL"), ("lead_bucket", "TEXT")],
        "candidates": [("contains_market_mode", "INTEGER NOT NULL DEFAULT 0")],
        "outcomes": [("prediction_prob", "REAL"), ("market_weight", "REAL")],
    }.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for name, kind in columns:
            if name not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {name} {kind}")
    existing = {row[1] for row in db.execute("PRAGMA table_info(candidates)")}
    for name, kind in [("prediction_probability", "REAL"), ("market_weight", "REAL")]:
        if name not in existing: db.execute(f"ALTER TABLE candidates ADD COLUMN {name} {kind}")
    existing = {row[1] for row in db.execute("PRAGMA table_info(paper_trades)")}
    for name, kind in [("prediction_probability", "REAL"), ("market_weight", "REAL")]:
        if name not in existing: db.execute(f"ALTER TABLE paper_trades ADD COLUMN {name} {kind}")
    return db


def save_snapshot(path, analysis, ranked, config):
    with connect(path) as db:
        cur = db.execute(
            """INSERT OR IGNORE INTO runs
               (captured_at,contract_date,slug,raw_weather_center_c,weather_center_c,
                weather_sigma_c,model_forecasts_json,config_json,hours_to_close,lead_bucket)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (analysis["as_of"], analysis["contract_date"], analysis["slug"],
             analysis.get("raw_weather_center_c"), analysis.get("weather_center_c"),
             analysis.get("weather_sigma_c"), json.dumps(analysis.get("model_forecasts_c", {})),
             json.dumps(config), config.get("hours_to_close"), config.get("lead_bucket")),
        )
        run_id = cur.lastrowid
        if not run_id:
            run_id = db.execute("SELECT id FROM runs WHERE captured_at=? AND slug=?",
                                (analysis["as_of"], analysis["slug"])).fetchone()[0]
        for row in analysis["ranking"]:
            db.execute("""INSERT OR REPLACE INTO outcomes
                (run_id,outcome,weather_prob,market_prob,best_bid,best_ask,bid_size,ask_size,
                 ask_levels_json,prediction_prob,market_weight) VALUES (?,?,?,?,?,?,?,?,?,?,?)""", (
                run_id, row["outcome"], row["weather_prob"], row.get("market_prob"),
                row.get("best_bid"), row.get("best_ask"), row.get("bid_size"), row.get("ask_size"),
                json.dumps(row.get("ask_levels", [])), row.get("prediction_prob"),
                row.get("market_weight")))
        for rank_no, item in enumerate(ranked, 1):
            db.execute("""INSERT OR REPLACE INTO candidates
                (run_id,rank_no,outcomes_json,legs_json,model_probability,executable_cost,
                 net_edge,qualifies,contains_model_mode,model_support_count,minimum_leg_price,
                 shares_per_outcome,contains_market_mode) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                run_id, rank_no, json.dumps(item["outcomes"], ensure_ascii=False),
                json.dumps(item["legs"], ensure_ascii=False), item["model_probability"],
                item["buy_cost_per_complete_basket"], item["net_edge"], int(item["qualifies"]),
                int(item["contains_model_mode"]), item["model_support_count"],
                item["minimum_leg_price"], item["shares_per_outcome"],
                int(item.get("contains_market_mode", False))))
            db.execute("UPDATE candidates SET prediction_probability=?,market_weight=? WHERE run_id=? AND rank_no=?",
                       (item.get("prediction_probability"), item.get("market_weight"), run_id, rank_no))
        return run_id


def record_paper_trade(path, run_id, analysis, item, bankroll, hours_to_close=None, lead_bucket=None):
    """Persist one simulated entry only after the formal Telegram alert succeeded."""
    shares = float(item["shares_per_outcome"])
    cost = float(item["buy_cost_per_complete_basket"])
    with connect(path) as db:
        db.execute("""INSERT OR IGNORE INTO paper_trades
          (run_id,notified_at,slug,contract_date,outcomes_json,legs_json,model_probability,
           executable_cost,net_edge,shares_per_outcome,stake_usd,bankroll_at_signal_usd,
           hours_to_close,lead_bucket)
          VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
            run_id, analysis["as_of"], analysis["slug"], analysis["contract_date"],
            json.dumps(item["outcomes"], ensure_ascii=False),
            json.dumps(item["legs"], ensure_ascii=False), item["model_probability"], cost,
            item["net_edge"], shares, cost * shares, bankroll, hours_to_close, lead_bucket))
        db.execute("UPDATE paper_trades SET prediction_probability=?,market_weight=? WHERE run_id=?",
                   (item.get("prediction_probability"), item.get("market_weight"), run_id))


def prior_market_probabilities(path, slug, before_iso):
    """Return the most recent archived market distribution before a cutoff."""
    with connect(path) as db:
        row = db.execute("SELECT id,captured_at FROM runs WHERE slug=? AND captured_at<=? ORDER BY captured_at DESC LIMIT 1",
                         (slug, before_iso)).fetchone()
        if not row: return None
        probabilities = dict(db.execute("SELECT outcome,market_prob FROM outcomes WHERE run_id=?", (row[0],)))
        return {"captured_at": row[1], "probabilities": probabilities}


def portfolio_state(path, starting_bankroll, current_slug):
    """Cash ledger using settled P&L and cost reserved by unresolved paper positions."""
    with connect(path) as db:
        rows = db.execute("""SELECT p.slug,p.outcomes_json,p.shares_per_outcome,p.stake_usd,
                                    z.winning_outcome
          FROM paper_trades p LEFT JOIN resolutions z ON z.slug=p.slug""").fetchall()
    settled_pnl = 0.0
    open_stake = 0.0
    current_contract_stake = 0.0
    for slug, outcomes_json, shares, stake, winner in rows:
        if winner is None:
            open_stake += stake
            if slug == current_slug:
                current_contract_stake += stake
        else:
            settled_pnl += (shares if winner in json.loads(outcomes_json) else 0.0) - stake
    equity = float(starting_bankroll) + settled_pnl
    return {"starting_bankroll_usd": float(starting_bankroll), "settled_pnl_usd": settled_pnl,
            "equity_usd": equity, "open_stake_usd": open_stake,
            "available_cash_usd": max(0.0, equity - open_stake),
            "current_contract_open_stake_usd": current_contract_stake}

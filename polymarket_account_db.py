#!/usr/bin/env python3
"""SQLite storage and aggregation for watched Polymarket account trades."""

import sqlite3
import time
from pathlib import Path


SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS account_trades (
  trade_key TEXT PRIMARY KEY,
  account_name TEXT NOT NULL,
  wallet TEXT NOT NULL,
  timestamp INTEGER NOT NULL,
  transaction_hash TEXT NOT NULL,
  token_id TEXT NOT NULL,
  condition_id TEXT NOT NULL,
  event_slug TEXT NOT NULL,
  market_slug TEXT NOT NULL,
  title TEXT NOT NULL,
  outcome TEXT NOT NULL,
  side TEXT NOT NULL CHECK(side IN ('BUY','SELL')),
  price REAL NOT NULL,
  size REAL NOT NULL,
  usdc_size REAL NOT NULL,
  received_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_trades_time ON account_trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_account_trades_target
  ON account_trades(account_name, token_id, timestamp DESC);
"""


def connect(path, read_only=False):
    path = Path(path)
    if read_only:
        db = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=10)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(path), timeout=30)
        db.executescript(SCHEMA)
    db.row_factory = sqlite3.Row
    return db


def record_trades(path, account_name, wallet, trades, key_function):
    if not trades:
        return 0
    db = connect(path)
    before = db.total_changes
    now = int(time.time())
    with db:
        for item in trades:
            db.execute(
                """INSERT OR IGNORE INTO account_trades
                (trade_key,account_name,wallet,timestamp,transaction_hash,token_id,
                 condition_id,event_slug,market_slug,title,outcome,side,price,size,
                 usdc_size,received_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    key_function(item), account_name, wallet,
                    int(item.get("timestamp") or 0), item.get("transaction_hash") or "",
                    item.get("token_id") or "", item.get("condition_id") or "",
                    item.get("event_slug") or "", item.get("slug") or "",
                    item.get("title") or "未知市场", item.get("outcome") or "未知",
                    item.get("side") or "BUY", float(item.get("price") or 0),
                    float(item.get("size") or 0),
                    float(item.get("usdc_size") or 0), now,
                ),
            )
    changes = db.total_changes - before
    db.close()
    return changes


def dashboard_data(path, account="all", query="", limit=300):
    db = connect(path, read_only=True)
    where, values = ["1=1"], []
    if account != "all":
        where.append("account_name = ?")
        values.append(account)
    if query:
        where.append("(title LIKE ? OR outcome LIKE ? OR event_slug LIKE ?)")
        needle = f"%{query}%"
        values.extend([needle, needle, needle])
    clause = " AND ".join(where)
    rows = db.execute(
        f"""SELECT account_name, wallet, token_id, title, outcome,
        MAX(event_slug) AS event_slug,
        MAX(market_slug) AS market_slug,
        SUM(CASE WHEN side='BUY' THEN usdc_size ELSE 0 END) AS buy_usdc,
        SUM(CASE WHEN side='SELL' THEN usdc_size ELSE 0 END) AS sell_usdc,
        SUM(CASE WHEN side='BUY' THEN size ELSE 0 END) AS buy_size,
        SUM(CASE WHEN side='SELL' THEN size ELSE 0 END) AS sell_size,
        SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) AS buy_count,
        SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) AS sell_count,
        COUNT(*) AS trade_count,
        MAX(timestamp) AS last_timestamp,
        CASE WHEN SUM(CASE WHEN side='BUY' THEN size ELSE 0 END) > 0
          THEN SUM(CASE WHEN side='BUY' THEN usdc_size ELSE 0 END) /
               SUM(CASE WHEN side='BUY' THEN size ELSE 0 END)
          ELSE 0 END AS avg_buy_price
        FROM account_trades WHERE {clause}
        GROUP BY account_name, wallet, token_id, title, outcome
        ORDER BY last_timestamp DESC LIMIT ?""",
        (*values, int(limit)),
    ).fetchall()
    totals = db.execute(
        f"""SELECT COUNT(*) AS trades,
        COUNT(DISTINCT account_name || ':' || token_id) AS targets,
        COALESCE(SUM(CASE WHEN side='BUY' THEN usdc_size ELSE 0 END),0) AS buy_usdc,
        COALESCE(SUM(CASE WHEN side='SELL' THEN usdc_size ELSE 0 END),0) AS sell_usdc,
        COALESCE(MAX(timestamp),0) AS last_timestamp
        FROM account_trades WHERE {clause}""",
        values,
    ).fetchone()
    accounts = [row[0] for row in db.execute(
        "SELECT DISTINCT account_name FROM account_trades ORDER BY account_name"
    )]
    db.close()
    groups = []
    for row in rows:
        item = dict(row)
        item["net_size"] = item["buy_size"] - item["sell_size"]
        item["is_repeated"] = item["buy_count"] >= 2
        item["size_tier"] = "large" if item["buy_usdc"] >= 100 else (
            "medium" if item["buy_usdc"] >= 50 else "small"
        )
        groups.append(item)
    return {
        "generated_at": int(time.time()),
        "totals": dict(totals),
        "accounts": accounts,
        "groups": groups,
    }

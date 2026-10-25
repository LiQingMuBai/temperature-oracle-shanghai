#!/usr/bin/env python3
"""Poll public Polymarket account trades and notify Telegram about new fills."""

import argparse
import datetime as dt
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent
API_URL = "https://data-api.polymarket.com/v2/activity"
SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_ACCOUNTS = {
    "241532532432": "0xce0b1054a2adb61a3efe8bcd42acc8d40154b974",
    "bilberry": "0xbf13934a1fec7d3211fc15c138d84ac2a691b91a",
}


def load_env(path):
    if not path or not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def atomic_write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def request_json(url):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "temperature-oracle-shanghai-account-watch/1.0"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        return json.load(response)


def fetch_trades(wallet, start, page_limit=500, max_pages=20):
    """Return trades oldest-first, including pagination for busy accounts."""
    params = {
        "user": wallet,
        "limit": page_limit,
        "type": "TRADE",
        "start": max(0, int(start)),
        "sortDirection": "ASC",
    }
    rows = []
    for _ in range(max_pages):
        payload = request_json(API_URL + "?" + urllib.parse.urlencode(params))
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise RuntimeError("Unexpected Polymarket activity response")
        rows.extend(payload["data"])
        pagination = payload.get("pagination") or {}
        cursor = pagination.get("next_cursor")
        if not pagination.get("has_more") or not cursor:
            return rows
        params["cursor"] = cursor
    raise RuntimeError("Polymarket activity pagination exceeded safety limit")


def trade_key(trade):
    fields = (
        trade.get("transaction_hash", ""),
        trade.get("token_id", ""),
        trade.get("side", ""),
        trade.get("size", ""),
        trade.get("price", ""),
        trade.get("timestamp", ""),
    )
    return hashlib.sha256("|".join(map(str, fields)).encode()).hexdigest()


def unseen_trades(trades, seen, started_at):
    known = set(seen)
    return [
        trade for trade in trades
        if int(trade.get("timestamp") or 0) >= int(started_at)
        and trade_key(trade) not in known
    ]


def trade_lines(trade):
    timestamp = dt.datetime.fromtimestamp(int(trade["timestamp"]), SHANGHAI)
    side = "买入" if trade.get("side") == "BUY" else "卖出"
    outcome = trade.get("outcome") or "未知方向"
    price = float(trade.get("price") or 0)
    size = float(trade.get("size") or 0)
    cash = float(trade.get("usdc_size") or price * size)
    slug = trade.get("event_slug") or trade.get("slug") or ""
    link = f"https://polymarket.com/event/{slug}" if slug else ""
    return [
        f"时间：{timestamp:%Y-%m-%d %H:%M:%S}（上海）",
        f"操作：{side} {outcome}",
        f"市场：{trade.get('title') or '未知市场'}",
        f"成交价：{price:.3f}（{price:.1%}）",
        f"份数：{size:g}",
        f"金额：${cash:.2f}",
        link,
    ]


def format_messages(name, trades, per_message=8):
    messages = []
    for offset in range(0, len(trades), per_message):
        group = trades[offset:offset + per_message]
        parts = [f"Polymarket账户新成交｜@{name}", f"本次发现：{len(trades)} 笔"]
        for index, trade in enumerate(group, offset + 1):
            parts.append("\n" + f"第 {index} 笔" + "\n" + "\n".join(trade_lines(trade)))
        if offset + per_message < len(trades):
            parts.append(f"\n其余成交将在下一条消息继续显示。")
        messages.append("\n".join(parts))
    return messages


def send_telegram(token, chat_id, message):
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": "true",
    }).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        result = json.load(response)
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected account-watch notification")


def configured_accounts():
    raw = os.getenv("POLYMARKET_WATCH_ACCOUNTS")
    if not raw:
        return DEFAULT_ACCOUNTS
    accounts = {}
    for item in raw.split(","):
        name, wallet = item.strip().split(":", 1)
        if not wallet.startswith("0x") or len(wallet) != 42:
            raise ValueError(f"Invalid wallet for {name}")
        accounts[name] = wallet.lower()
    return accounts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / "work" / "telegram.env")
    parser.add_argument("--state-file", type=Path, default=ROOT / "work" / "polymarket_account_watch_state.json")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_env(args.env_file)
    accounts = configured_accounts()
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not args.dry_run and (not token or not chat_id):
        raise RuntimeError("Telegram credentials are not configured")

    now = int(time.time())
    if not args.state_file.exists():
        # Validate every account and retain current rows as a no-alert baseline.
        account_state = {}
        for name, wallet in accounts.items():
            recent = fetch_trades(wallet, now)
            account_state[name] = {
                "wallet": wallet,
                "last_timestamp": now,
                "seen": [trade_key(item) for item in recent][-5000:],
            }
        state = {"version": 1, "started_at": now, "accounts": account_state}
        if not args.dry_run:
            atomic_write(args.state_file, state)
        print(json.dumps({"status": "baseline_created", "started_at": now,
                          "accounts": list(accounts)}, ensure_ascii=False))
        return

    state = json.loads(args.state_file.read_text(encoding="utf-8"))
    started_at = int(state.get("started_at") or now)
    summaries = []
    for name, wallet in accounts.items():
        saved = state.setdefault("accounts", {}).setdefault(name, {
            "wallet": wallet, "last_timestamp": started_at, "seen": [],
        })
        saved["wallet"] = wallet
        query_start = max(started_at, int(saved.get("last_timestamp") or started_at) - 2)
        trades = fetch_trades(wallet, query_start)
        fresh = unseen_trades(trades, saved.get("seen", []), started_at)
        fresh.sort(key=lambda item: (int(item.get("timestamp") or 0), trade_key(item)))
        if args.dry_run:
            summaries.append({"account": name, "new_trades": len(fresh)})
            continue
        for message in format_messages(name, fresh):
            send_telegram(token, chat_id, message)
        seen = list(saved.get("seen", [])) + [trade_key(item) for item in fresh]
        saved["seen"] = list(dict.fromkeys(seen))[-5000:]
        if trades:
            saved["last_timestamp"] = max(
                int(saved.get("last_timestamp") or started_at),
                max(int(item.get("timestamp") or 0) for item in trades),
            )
        saved["last_checked_at"] = now
        atomic_write(args.state_file, state)
        summaries.append({"account": name, "new_trades": len(fresh)})
    print(json.dumps({"status": "ok", "checked_at": now, "accounts": summaries}, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"account watch failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise

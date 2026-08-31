#!/usr/bin/env python3
"""Alert on executable Shanghai temperature-market basket edges."""
import argparse
import datetime as dt
import json
import math
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo
from polymarket_snapshot_db import portfolio_state, prior_market_probabilities, record_paper_trade, record_shadow_trades, save_snapshot
from zspd_observations import current_day_max

ROOT = Path(__file__).resolve().parent
def load_env(path):
    if not path or not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def tomorrow_slug(now=None):
    today = (now or dt.datetime.now(ZoneInfo("Asia/Shanghai"))).date()
    target = today + dt.timedelta(days=1)
    slug = f"highest-temperature-in-shanghai-on-{target.strftime('%B').lower()}-{target.day}-{target.year}"
    return target.isoformat(), slug


def lead_layer(event_end_at, now=None):
    end = dt.datetime.fromisoformat(event_end_at.replace("Z", "+00:00"))
    current = now or dt.datetime.now(dt.timezone.utc)
    hours = (end - current.astimezone(dt.timezone.utc)).total_seconds() / 3600
    if hours <= 4.5: bucket = "3h"
    elif hours <= 9: bucket = "6h"
    elif hours <= 18: bucket = "12h"
    else: bucket = "24h"
    return hours, bucket


def run_analysis(slug, target):
    command = [sys.executable, str(ROOT / "polymarket_analysis.py"), "--slug", slug, "--date", target]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Polymarket analysis failed")
    return json.loads(result.stdout)


def temperature_key(label):
    match = re.search(r"-?\d+", label)
    return int(match.group()) if match else 999


def outcome_for_temperature(labels, value):
    integer = int(value + 0.5)
    for label in labels:
        boundary = temperature_key(label)
        if "below" in label and integer <= boundary:
            return label
        if "higher" in label and integer >= boundary:
            return label
        if "below" not in label and "higher" not in label and integer == boundary:
            return label
    return None


def condition_on_observed_max(analysis, observed_max_c):
    """Condition final daily maximum probabilities on Tmax already observed today."""
    for row in analysis["ranking"]:
        label = row["outcome"]
        boundary = temperature_key(label)
        impossible = ("below" in label and boundary < observed_max_c) or (
            "below" not in label and "higher" not in label and boundary < observed_max_c)
        if impossible:
            row["weather_prob"] = 0.0
    total = sum(float(row["weather_prob"]) for row in analysis["ranking"])
    if total > 0:
        for row in analysis["ranking"]:
            row["weather_prob"] = float(row["weather_prob"]) / total
    analysis["unconditioned_model_forecasts_c"] = dict(analysis.get("model_forecasts_c", {}))
    analysis["model_forecasts_c"] = {
        name: max(float(value), observed_max_c)
        for name, value in analysis.get("model_forecasts_c", {}).items()}


def apply_market_fusion(analysis, lead_bucket, prior=None):
    """Market-informed prediction probability; independent weather probability stays unchanged for edge."""
    rows = analysis["ranking"]
    base_weight = {"24h": .35, "12h": .50, "6h": .60, "3h": .70}[lead_bucket]
    weighted_spread = sum(float(r.get("market_prob", 0)) * float(r.get("spread", 1)) for r in rows)
    depth = sum(float(r.get("market_prob", 0)) * (float(r.get("bid_size", 0)) + float(r.get("ask_size", 0))) for r in rows)
    spread_quality = max(.2, min(1., 1 - weighted_spread / .20))
    depth_quality = max(.2, min(1., math.log1p(depth) / math.log(201)))
    market_weight = base_weight * math.sqrt(spread_quality * depth_quality)
    prior_probs = prior["probabilities"] if prior else {}
    trended = {}
    for row in rows:
        current = float(row.get("market_prob") or 0)
        old = prior_probs.get(row["outcome"])
        # Half-strength two-hour extrapolation, bounded by non-negativity and later normalization.
        trended[row["outcome"]] = max(1e-8, current + .5 * (current - float(old))) if old is not None else max(1e-8, current)
    total_market = sum(trended.values())
    raw=[]
    for row in rows:
        market_signal = trended[row["outcome"]] / total_market
        value = max(float(row["weather_prob"]), 1e-8) ** (1-market_weight) * max(market_signal, 1e-8) ** market_weight
        raw.append(value)
    total=sum(raw)
    for row,value in zip(rows,raw):
        row["prediction_prob"] = value / total
        row["market_weight"] = market_weight
    return {"market_weight":market_weight,"base_weight":base_weight,
            "spread_quality":spread_quality,"depth_quality":depth_quality,
            "trend_reference_at":prior.get("captured_at") if prior else None}


def fill_cost(levels, shares):
    remaining = shares
    cost = 0.0
    for level in sorted(levels, key=lambda x: float(x["price"])):
        price, size = float(level["price"]), float(level["size"])
        take = min(remaining, size)
        cost += take * price
        remaining -= take
        if remaining <= 1e-9:
            return cost
    return None


def execution_limit(levels, shares):
    """Highest ask consumed when filling the requested number of shares."""
    remaining = shares
    for level in sorted(levels, key=lambda x: float(x["price"])):
        price, size = float(level["price"]), float(level["size"])
        remaining -= min(remaining, size)
        if remaining <= 1e-9:
            return price
    return None


def candidates(analysis, shares, threshold, min_probability=0.50, require_mode=False,
               min_model_support=1, min_leg_price=0.001):
    rows = sorted(analysis["ranking"], key=lambda row: temperature_key(row["outcome"]))
    mode_outcome = max(rows, key=lambda row: float(row["weather_prob"]))["outcome"]
    market_mode_outcome = max(
        rows, key=lambda row: float(row.get("market_prob") or row["weather_prob"]))["outcome"]
    prediction_mode_outcome = max(
        rows, key=lambda row: float(row.get("prediction_prob") or row["weather_prob"]))["outcome"]
    mode_gap = abs(temperature_key(mode_outcome) - temperature_key(market_mode_outcome))
    labels = [row["outcome"] for row in rows]
    found = []
    for width in (2, 3, 4):
        for start in range(len(rows) - width + 1):
            basket = rows[start:start + width]
            fills = [fill_cost(row.get("ask_levels", []), shares) for row in basket]
            if any(fill is None for fill in fills):
                continue
            model_probability = sum(float(row["weather_prob"]) for row in basket)
            prediction_probability = sum(float(row.get("prediction_prob") or row["weather_prob"]) for row in basket)
            gross_cost = sum(fills)
            # One complete basket pays `shares` dollars when any selected bin wins.
            edge_dollars = shares * model_probability - gross_cost
            edge = edge_dollars / shares
            outcomes = [row["outcome"] for row in basket]
            supporting_models = [name for name, value in analysis.get("model_forecasts_c", {}).items()
                                 if outcome_for_temperature(labels, float(value)) in outcomes]
            limits = [execution_limit(row.get("ask_levels", []), shares) for row in basket]
            item = {
                "outcomes": outcomes,
                "legs": [{
                    "outcome": row["outcome"],
                    "side": "YES",
                    "shares": shares,
                    "limit_price": limit,
                    "estimated_vwap": fill / shares,
                } for row, fill, limit in zip(basket, fills, limits)],
                "shares_per_outcome": shares,
                "model_probability": model_probability,
                "prediction_probability": prediction_probability,
                "market_weight": float(basket[0].get("market_weight") or 0),
                "buy_cost_per_complete_basket": gross_cost / shares,
                "net_edge": edge,
                "contains_model_mode": mode_outcome in outcomes,
                "contains_market_mode": market_mode_outcome in outcomes,
                "model_mode_outcome": mode_outcome,
                "market_mode_outcome": market_mode_outcome,
                "prediction_mode_outcome": prediction_mode_outcome,
                "weather_market_mode_gap_c": mode_gap,
                "supporting_models": supporting_models,
                "model_support_count": len(supporting_models),
                "minimum_leg_price": min(limits),
            }
            item["qualifies"] = (
                edge >= threshold
                and prediction_probability >= min_probability
                and (item["contains_model_mode"] or not require_mode)
                and item["contains_market_mode"]
                and mode_gap <= 3
                and len(supporting_models) >= min_model_support
                and min(limits) >= min_leg_price
            )
            found.append(item)
    return sorted(found, key=lambda item: (item["qualifies"], item["net_edge"]), reverse=True)


def send_telegram(token, chat_id, message):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "disable_web_page_preview": "true"}).encode()
    request = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read())
    if not result.get("ok"):
        raise RuntimeError("Telegram rejected the message")


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def format_alert(analysis, item):
    labels = " + ".join(item["outcomes"])
    orders = "\n".join(
        f"• 买 YES {leg['outcome']}：{leg['shares']:g} 份，限价 ≤ ${leg['limit_price']:.3f}"
        for leg in item["legs"]
    )
    total_cash = item["shares_per_outcome"] * item["buy_cost_per_complete_basket"]
    bankroll = float(os.getenv("POLYMARKET_BANKROLL_USD", "10"))
    stake_pct = total_cash / bankroll if bankroll > 0 else 0
    available_before = float(item.get("portfolio_available_cash_usd", bankroll))
    remaining_cash = max(0, available_before - total_cash)
    gross_payout = item["shares_per_outcome"]
    profit_if_hit = gross_payout - total_cash
    observation = analysis.get("current_day_observation")
    observation_line = (f"今日ZSPD已观测最高温：{observation['max_temp_c']:.1f}°C\n"
                        if observation and observation.get("applied") else "")
    return (
        "上海最高温组合出现量化信号\n"
        f"日期：{analysis['contract_date']}\n"
        f"{observation_line}"
        f"组合：{labels}\n"
        f"模型组合概率：{item['model_probability']:.1%}\n"
        f"市场融合预测概率：{item['prediction_probability']:.1%}\n"
        f"可成交买入成本：{item['buy_cost_per_complete_basket']:.1%}\n"
        f"净优势：{item['net_edge']:.1%}\n"
        f"深度口径：每档 {item['shares_per_outcome']:g} 份\n"
        "\n参考执行清单：\n"
        f"{orders}\n"
        f"预计买入总成本：${total_cash:.2f}\n"
        "\n10美元资金计划：\n"
        f"• 本次投入：${total_cash:.2f}（初始资产的 {stake_pct:.1%}）\n"
        f"• 下单前可用现金：${available_before:.2f}\n"
        f"• 下单后保留现金：${remaining_cash:.2f}\n"
        f"• 最坏亏损：${total_cash:.2f}\n"
        f"• 任一所选档命中：预计回款 ${gross_payout:.2f}，毛利润 ${profit_if_hit:.2f}\n"
        "执行规则：全部档位同时满足限价才买；任一档超过限价则放弃并等待下次信号。不要用市价单。\n"
        f"https://polymarket.com/event/{analysis['slug']}\n"
        "仅为模型信号，不保证盈利。"
    )


def format_no_signal(analysis, item, threshold, min_probability, min_model_support, min_leg_price):
    if not item:
        detail = "当前盘口深度不足，无法形成可成交组合。"
    else:
        reasons = []
        if item["net_edge"] < threshold:
            reasons.append(f"净优势 {item['net_edge']:.1%} < {threshold:.0%}")
        if item.get("prediction_probability", item["model_probability"]) < min_probability:
            reasons.append(f"融合概率 {item.get('prediction_probability',item['model_probability']):.1%} < {min_probability:.0%}")
        if not item.get("contains_market_mode"):
            reasons.append("未包含盘口最高概率温度档")
        if item.get("weather_market_mode_gap_c", 0) > 3:
            reasons.append("天气与盘口众数相差超过3°C")
        if item["model_support_count"] < min_model_support:
            reasons.append(f"仅 {item['model_support_count']} 个模式支持，要求至少 {min_model_support} 个")
        if item["minimum_leg_price"] < min_leg_price:
            reasons.append(f"存在低于 {min_leg_price:.0%} 的廉价尾部档")
        if item.get("capital_rejection"):
            reasons.append("可用现金或单合约风险额度不足")
        if item.get("layer_rejection"):
            reasons.append("该时间层当前只观察、不下注")
        detail = (
            f"最接近组合：{' + '.join(item['outcomes'])}\n"
            f"天气概率：{item['model_probability']:.1%}；融合概率：{item.get('prediction_probability',item['model_probability']):.1%}；买入成本：{item['buy_cost_per_complete_basket']:.1%}\n"
            f"未通过：{'；'.join(reasons) if reasons else '稳健性规则'}"
        )
    observation = analysis.get("current_day_observation")
    observation_line = (f"今日ZSPD已观测最高温：{observation['max_temp_c']:.1f}°C\n"
                        if observation and observation.get("applied") else "")
    return (
        "上海最高温监控：当前没有下注机会\n"
        f"日期：{analysis['contract_date']}\n"
        f"{observation_line}"
        f"{detail}\n"
        f"https://polymarket.com/event/{analysis['slug']}\n"
        "系统将继续每15分钟检查。"
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / "work" / "telegram.env")
    parser.add_argument("--slug")
    parser.add_argument("--date")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    load_env(args.env_file)
    target, default_slug = tomorrow_slug()
    target, slug = args.date or target, args.slug or default_slug
    shares = float(os.getenv("POLYMARKET_SHARES_PER_OUTCOME", "10"))
    bankroll = float(os.getenv("POLYMARKET_BANKROLL_USD", "10"))
    threshold = float(os.getenv("POLYMARKET_MIN_NET_EDGE", "0.10"))
    min_probability = float(os.getenv("POLYMARKET_MIN_COMBO_PROBABILITY", "0.50"))
    min_model_support = int(os.getenv("POLYMARKET_MIN_MODEL_SUPPORT", "1"))
    min_leg_price = float(os.getenv("POLYMARKET_MIN_LEG_PRICE", "0.001"))
    no_signal_hours = float(os.getenv("POLYMARKET_NO_SIGNAL_NOTICE_HOURS", "6"))
    max_contract_fraction = float(os.getenv("POLYMARKET_MAX_CONTRACT_EXPOSURE", "0.30"))
    minimum_order_shares = int(os.getenv("POLYMARKET_MIN_ORDER_SHARES", "5"))
    snapshot_db = Path(os.getenv("POLYMARKET_SNAPSHOT_DB", ROOT / "work" / "polymarket_snapshots.sqlite3"))
    analysis = run_analysis(slug, target)
    hours_to_close, lead_bucket = lead_layer(analysis["event_end_at"])
    if hours_to_close <= 0:
        print(json.dumps({"slug": slug, "status": "market close time passed"}, ensure_ascii=False))
        return
    today = dt.datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    if target == today and lead_bucket in ("6h", "3h"):
        try:
            observation = current_day_max(target)
        except Exception as exc:
            observation = {"error": type(exc).__name__, "applied": False}
        if observation:
            observation["applied"] = observation.get("age_hours", 99) <= 2
            analysis["current_day_observation"] = observation
            if observation["applied"]:
                condition_on_observed_max(analysis, observation["max_temp_c"])
    cutoff = (dt.datetime.fromisoformat(analysis["as_of"]) - dt.timedelta(hours=1.5)).isoformat()
    prior_market = prior_market_probabilities(snapshot_db, slug, cutoff)
    market_fusion = apply_market_fusion(analysis, lead_bucket, prior_market)
    layer_defaults = {"24h": (0.60, 0.10), "12h": (0.50, 0.03),
                      "6h": (0.55, 0.02), "3h": (0.60, 0.01)}
    default_probability, default_edge = layer_defaults[lead_bucket]
    min_probability = float(os.getenv(f"POLYMARKET_{lead_bucket.upper()}_MIN_PROBABILITY", default_probability))
    threshold = float(os.getenv(f"POLYMARKET_{lead_bucket.upper()}_MIN_EDGE", default_edge))
    layer_enabled = os.getenv(f"POLYMARKET_{lead_bucket.upper()}_ENABLED",
                              "0" if lead_bucket == "24h" else "1") == "1"
    ranked = candidates(analysis, shares, threshold, min_probability, require_mode=False,
                        min_model_support=min_model_support, min_leg_price=min_leg_price)
    best = ranked[0] if ranked else None
    if not layer_enabled:
        for item in ranked:
            item["qualifies"] = False
            item["layer_rejection"] = f"{lead_bucket} trading disabled"
        best = ranked[0] if ranked else None
    portfolio = portfolio_state(snapshot_db, bankroll, slug)
    contract_limit = max(0.0, portfolio["equity_usd"] * max_contract_fraction)
    order_budget = min(portfolio["available_cash_usd"],
                       max(0.0, contract_limit - portfolio["current_contract_open_stake_usd"]))
    # Reduce equal shares when the otherwise-qualified order exceeds available/risk capital.
    if best and best["qualifies"]:
        planned = shares * best["buy_cost_per_complete_basket"]
        if planned > order_budget:
            affordable_shares = int(order_budget / best["buy_cost_per_complete_basket"])
            if affordable_shares >= minimum_order_shares:
                shares = float(min(shares, affordable_shares))
                ranked = candidates(analysis, shares, threshold, min_probability, require_mode=False,
                                    min_model_support=min_model_support, min_leg_price=min_leg_price)
                best = ranked[0] if ranked else None
            else:
                best["qualifies"] = False
                best["capital_rejection"] = "insufficient cash or per-contract risk budget"
    if best:
        best["bankroll_usd"] = bankroll
        best["planned_stake_usd"] = shares * best["buy_cost_per_complete_basket"]
        best["stake_fraction"] = best["planned_stake_usd"] / bankroll if bankroll > 0 else None
        best["order_budget_usd"] = order_budget
        best["portfolio_available_cash_usd"] = portfolio["available_cash_usd"]
        best["portfolio_equity_usd"] = portfolio["equity_usd"]
        best["portfolio_after_order_cash_usd"] = max(0.0, portfolio["available_cash_usd"] - best["planned_stake_usd"])
    result = {"checked_at": analysis["as_of"], "slug": slug, "threshold": threshold,
              "minimum_combo_probability": min_probability, "require_model_mode": False,
              "minimum_model_support": min_model_support, "minimum_leg_price": min_leg_price,
              "max_contract_exposure": max_contract_fraction, "portfolio": portfolio, "best": best}
    result["market_fusion"] = market_fusion
    result["layer_trading_enabled"] = layer_enabled
    result["hours_to_close"] = hours_to_close
    result["lead_bucket"] = lead_bucket
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.dry_run:
        return

    snapshot_run_id = save_snapshot(snapshot_db, analysis, ranked, {
        "threshold": threshold, "minimum_combo_probability": min_probability,
        "require_model_mode": False, "minimum_model_support": min_model_support,
        "minimum_leg_price": min_leg_price, "shares_per_outcome": shares,
        "bankroll_usd": bankroll, "maximum_contract_exposure": max_contract_fraction,
        "minimum_order_shares": minimum_order_shares, "portfolio": portfolio,
        "hours_to_close": hours_to_close, "lead_bucket": lead_bucket,
        "layer_trading_enabled": layer_enabled,
        "current_day_observation": analysis.get("current_day_observation"),
        "market_fusion": market_fusion,
    })
    shadow_entries = record_shadow_trades(snapshot_db, snapshot_run_id, analysis, ranked, lead_bucket)
    if shadow_entries:
        print(json.dumps({"shadow_entries_recorded": shadow_entries}, ensure_ascii=False))

    state_path = ROOT / "work" / f"telegram_monitor_state_{target}.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    qualified = best if best and best["qualifies"] else None
    signal_id = "|".join(qualified["outcomes"]) if qualified else None
    prior_edge_value = previous.get("edge")
    prior_edge = float(prior_edge_value) if prior_edge_value is not None else -99.0
    should_alert = bool(qualified) and (
        not previous.get("active") or previous.get("signal_id") != signal_id
        or qualified["net_edge"] >= prior_edge + 0.02
    )
    token, chat_id = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    sent = False
    if should_alert and token and chat_id:
        send_telegram(token, chat_id, format_alert(analysis, qualified))
        record_paper_trade(snapshot_db, snapshot_run_id, analysis, qualified, bankroll,
                           hours_to_close, lead_bucket)
        sent = True
    now_epoch = time.time()
    last_no_signal_notice = float(previous.get("last_no_signal_notice") or 0)
    should_send_no_signal = (
        not qualified and token and chat_id
        and (previous.get("active") or now_epoch - last_no_signal_notice >= no_signal_hours * 3600)
    )
    no_signal_sent = False
    if should_send_no_signal:
        send_telegram(token, chat_id, format_no_signal(
            analysis, best, threshold, min_probability, min_model_support, min_leg_price))
        no_signal_sent = True
    prior_signal_still_active = bool(qualified) and previous.get("active") and previous.get("signal_id") == signal_id
    atomic_write(state_path, {
        # Missing credentials must not consume the crossing; configuration later should send it.
        "active": bool(sent or prior_signal_still_active), "signal_id": signal_id,
        "edge": qualified["net_edge"] if qualified else None,
        "alert_sent": sent, "checked_at": analysis["as_of"],
        "no_signal_notice_sent": no_signal_sent,
        "last_no_signal_notice": now_epoch if no_signal_sent else last_no_signal_notice,
        "credentials_configured": bool(token and chat_id),
    })
    if should_alert and not sent:
        print("Signal qualifies, but Telegram credentials are not configured.", file=sys.stderr)


if __name__ == "__main__":
    main()

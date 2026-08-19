#!/usr/bin/env python3
"""上海次日最高气温量化决策系统（仅依赖 Python 标准库）。"""
from __future__ import annotations

import argparse, csv, datetime as dt, json, math, os, statistics, sys
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUTPUTS = ROOT / "outputs"
LAT, LON, TZ = 31.2304, 121.4737, "Asia/Shanghai"
FEATURES = ["bias", "sin", "cos", "lag1", "lag2", "lag7", "mean7", "mean30", "trend7"]


def fetch_json(base, params):
    req = base + "?" + urlencode(params, safe=",")
    with urlopen(req, timeout=60) as r:
        return json.load(r)


def update_data(start="2010-01-01", end=None):
    """下载上海中心点逐日再分析数据。"""
    end = end or (dt.date.today() - dt.timedelta(days=6)).isoformat()
    obj = fetch_json("https://archive-api.open-meteo.com/v1/archive", {
        "latitude": LAT, "longitude": LON, "start_date": start, "end_date": end,
        "daily": "temperature_2m_max", "timezone": TZ,
    })
    DATA.mkdir(exist_ok=True)
    path = DATA / "shanghai_tmax.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f); w.writerow(["date", "tmax"])
        for d, y in zip(obj["daily"]["time"], obj["daily"]["temperature_2m_max"]):
            if y is not None: w.writerow([d, y])
    return path


def load_rows(path=None):
    path = Path(path or DATA / "shanghai_tmax.csv")
    with path.open(encoding="utf-8") as f:
        return [(dt.date.fromisoformat(r["date"]), float(r["tmax"])) for r in csv.DictReader(f)]


def feat(vals, target_date):
    if len(vals) < 30: return None
    doy = target_date.timetuple().tm_yday
    a = 2 * math.pi * doy / 365.2425
    m7, m30 = statistics.mean(vals[-7:]), statistics.mean(vals[-30:])
    return [1.0, math.sin(a), math.cos(a), vals[-1], vals[-2], vals[-7], m7, m30,
            statistics.mean(vals[-3:]) - statistics.mean(vals[-7:-4])]


def solve(a, b):
    """带主元选择的高斯消元。"""
    n = len(b); m = [a[i][:] + [b[i]] for i in range(n)]
    for k in range(n):
        p = max(range(k, n), key=lambda i: abs(m[i][k])); m[k], m[p] = m[p], m[k]
        if abs(m[k][k]) < 1e-12: m[k][k] = 1e-12
        for i in range(k + 1, n):
            q = m[i][k] / m[k][k]
            for j in range(k, n + 1): m[i][j] -= q * m[k][j]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


def fit_ridge(xs, ys, alpha=20.0):
    # 标准化可防止温度特征量纲主导正则项；截距不正则化。
    p = len(xs[0]); means = [statistics.mean(x[j] for x in xs) for j in range(p)]
    scales = [statistics.pstdev(x[j] for x in xs) or 1.0 for j in range(p)]
    means[0], scales[0] = 0.0, 1.0
    z = [[(x[j]-means[j])/scales[j] for j in range(p)] for x in xs]
    a = [[sum(r[i]*r[j] for r in z) + (alpha if i == j and i else 0) for j in range(p)] for i in range(p)]
    b = [sum(r[i]*y for r, y in zip(z, ys)) for i in range(p)]
    return solve(a, b), means, scales


def predict(model, x):
    beta, means, scales = model
    return sum(b * ((v-means[i])/scales[i]) for i, (b, v) in enumerate(zip(beta, x)))


def metrics(rows, threshold=35.0):
    e = [r["pred"] - r["actual"] for r in rows]
    tp = sum(r["pred"] >= threshold and r["actual"] >= threshold for r in rows)
    fn = sum(r["pred"] < threshold and r["actual"] >= threshold for r in rows)
    return {"n": len(rows), "mae": round(statistics.mean(map(abs, e)), 3),
            "rmse": round(math.sqrt(statistics.mean(v*v for v in e)), 3),
            "bias": round(statistics.mean(e), 3),
            "within_2c": round(sum(abs(v) <= 2 for v in e)/len(e), 3),
            "heat_recall": round(tp/(tp+fn), 3) if tp+fn else None}


def alert_metrics(rows, event_threshold=35.0, alert_threshold=33.0):
    tp = sum(r["pred"] >= alert_threshold and r["actual"] >= event_threshold for r in rows)
    fp = sum(r["pred"] >= alert_threshold and r["actual"] < event_threshold for r in rows)
    fn = sum(r["pred"] < alert_threshold and r["actual"] >= event_threshold for r in rows)
    tn = len(rows)-tp-fp-fn
    return {"alert_threshold_c": alert_threshold,
            "recall": round(tp/(tp+fn), 3) if tp+fn else None,
            "precision": round(tp/(tp+fp), 3) if tp+fp else None,
            "false_alarm_rate": round(fp/(fp+tn), 3) if fp+tn else None}


def backtest(rows, start_year=2018, retrain_days=30, threshold=35.0):
    preds, model, last_fit = [], None, -10**9
    values = [y for _, y in rows]
    for i in range(30, len(rows)):
        date, actual = rows[i]
        if date.year < start_year: continue
        if model is None or i-last_fit >= retrain_days:
            xs, ys = [], []
            for j in range(30, i):
                x = feat(values[:j], rows[j][0])
                if x: xs.append(x); ys.append(values[j])
            model, last_fit = fit_ridge(xs, ys), i
        x = feat(values[:i], date)
        pred = predict(model, x)
        prior = [(d, y) for d, y in rows[:i] if abs((d.timetuple().tm_yday-date.timetuple().tm_yday+182)%365-182) <= 15]
        climatology = statistics.mean(y for _, y in prior) if prior else statistics.mean(values[:i])
        preds.append({"date": date.isoformat(), "actual": actual, "pred": round(pred, 3),
                      "persistence": values[i-1], "climatology": round(climatology, 3),
                      "signal": decision(pred, threshold)["level"]})
    OUTPUTS.mkdir(exist_ok=True)
    detail = OUTPUTS / "backtest_predictions.csv"
    with detail.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=preds[0].keys()); w.writeheader(); w.writerows(preds)
    model_m = metrics(preds, threshold)
    base = [{**r, "pred": r["persistence"]} for r in preds]
    climate = [{**r, "pred": r["climatology"]} for r in preds]
    report = {"method": "expanding-window walk-forward", "start_year": start_year,
              "threshold_c": threshold, "ridge": model_m,
              "yellow_alert_for_heat_event": alert_metrics(preds, threshold, threshold-2),
              "persistence": metrics(base, threshold), "seasonal_climatology": metrics(climate, threshold),
              "skill_mae_vs_persistence": round(1-model_m["mae"]/metrics(base, threshold)["mae"], 3),
              "detail": str(detail)}
    (OUTPUTS / "backtest_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def decision(t, threshold=35.0):
    if t >= threshold + 2: return {"level":"红色", "action":"启动高温应急；室外作业避开11–16时；核查制冷容量"}
    if t >= threshold: return {"level":"橙色", "action":"发布高温准备信号；调整排班；锁定制冷负荷"}
    if t >= threshold - 2: return {"level":"黄色", "action":"关注预报更新；准备弹性排班与制冷资源"}
    return {"level":"绿色", "action":"常规运行"}


def live_forecast(rows, threshold=35.0):
    obj = fetch_json("https://api.open-meteo.com/v1/forecast", {
        "latitude": LAT, "longitude": LON, "daily": "temperature_2m_max",
        "forecast_days": 3, "timezone": TZ,
    })
    values = [y for _, y in rows]; xs, ys = [], []
    for i in range(30, len(rows)):
        xs.append(feat(values[:i], rows[i][0])); ys.append(values[i])
    model = fit_ridge(xs, ys)
    date = dt.date.fromisoformat(obj["daily"]["time"][1])
    stat = predict(model, feat(values, date)); nwp = float(obj["daily"]["temperature_2m_max"][1])
    # NWP 为主，统计模型作为稳健校正；区间为经验风险带，不冒充概率校准区间。
    blended = 0.75*nwp + 0.25*stat
    result = {"target_date": date.isoformat(), "nwp_c": round(nwp,1), "statistical_c": round(stat,1),
              "final_c": round(blended,1), "risk_band_c": [round(blended-2,1), round(blended+2,1)],
              "decision": decision(blended, threshold), "generated_at": dt.datetime.now().astimezone().isoformat()}
    OUTPUTS.mkdir(exist_ok=True)
    (OUTPUTS / "latest_forecast.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__); sub = p.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update"); u.add_argument("--start", default="2010-01-01")
    b = sub.add_parser("backtest"); b.add_argument("--start-year", type=int, default=2018); b.add_argument("--threshold", type=float, default=35)
    f = sub.add_parser("forecast"); f.add_argument("--threshold", type=float, default=35)
    a = p.parse_args()
    if a.cmd == "update": out = {"data": str(update_data(a.start))}
    else:
        if not (DATA / "shanghai_tmax.csv").exists(): update_data()
        rows = load_rows()
        out = backtest(rows, a.start_year, threshold=a.threshold) if a.cmd == "backtest" else live_forecast(rows, a.threshold)
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()

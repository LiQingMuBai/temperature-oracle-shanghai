# Shanghai Maximum Temperature Oracle

**English** | [简体中文](README.zh-CN.md)

See [DEPLOY_UBUNTU.md](DEPLOY_UBUNTU.md) for Ubuntu deployment instructions.

This is a dependency-free, auditable system for forecasting Shanghai's next-day maximum temperature, combining weather probabilities with live Polymarket order-book data, and delivering risk-filtered signals through Telegram. It never places real orders automatically.

## Weather Underground / ZSPD Backtest

```bash
python3 wu_backtest.py download --start-year 2015
python3 wu_backtest.py backtest --start-year 2020
```

Data is stored in `data/wu_zspd_daily_c.csv`; reports and daily predictions are written to `outputs/`. The integer-bin model uses nested walk-forward validation and reports accuracy, log loss, and multiclass Brier score.

## Archived Numerical Weather Prediction Backtest

```bash
python3 nwp_backtest.py download --start 2024-01-01
python3 nwp_backtest.py backtest
python3 enhanced_nwp.py download --start 2024-01-01
python3 enhanced_nwp.py backtest
```

The system uses fixed D+1/D+2 archived forecasts from the Open-Meteo Previous Runs API. It compares GFS, ECMWF, CMA, JMA, and a rolling bias-corrected ensemble. The enhanced model adds dew point, cloud cover, shortwave radiation, precipitation, wind vectors, and heat interactions.

## Quick Start

```bash
python3 app.py update --start 2010-01-01
python3 app.py backtest --start-year 2018 --threshold 35
python3 app.py forecast --threshold 35
python3 polymarket_analysis.py
```

## Backtest Definition

- Target: predict next-day maximum temperature using only information available before the target day.
- Split: expanding-window daily backtest with no random shuffling.
- Baselines: previous-day persistence and seasonal climatology.
- Metrics: MAE, RMSE, bias, ±2°C accuracy, integer-bin accuracy, Brier score, and log loss.

## Telegram Polymarket Signals

The monitor automatically selects the next-day market in the Asia/Shanghai timezone and scans adjacent two-bin and three-bin baskets. A formal betting signal must satisfy every rule:

- combined model probability of at least 50%;
- includes the model's highest-probability temperature bin;
- supported by at least three raw weather models;
- every executable leg is priced at 1¢ or higher;
- model probability minus executable basket cost is at least 10%;
- cumulative exposure for one daily contract does not exceed 20% of current equity.

Historical bias correction is capped at ±1°C relative to the current raw multi-model center. Equal-share orders are evaluated against actual order-book depth. The system does not place orders.

Setup:

1. Create a Telegram bot with `@BotFather` and obtain a token.
2. Copy `telegram.env.example` to `work/telegram.env`, then enter the token and chat ID.
3. Run a read-only check:

```bash
python3 telegram_polymarket_monitor.py --dry-run
```

Run the live notifier:

```bash
python3 telegram_polymarket_monitor.py --env-file work/telegram.env
```

Opportunity alerts include order legs, limits, capital allocation, and maximum loss. When no opportunity qualifies, a status notification is sent at most once every six hours. Duplicate signals are suppressed.

## Capital Management

The default starting bankroll is USD 10:

- settled P&L changes equity;
- unresolved paper positions reserve cash;
- exposure per daily contract is capped at 20% of equity;
- the default target is ten shares per leg and is reduced when the budget is insufficient;
- a signal is rejected if it cannot satisfy the minimum five-share order.

## Point-in-Time Snapshots and Trade-Level Rolling Backtest

Every live monitoring run stores the model state, probabilities, per-bin quotes, full ask depth, candidates, and filter decisions in `work/polymarket_snapshots.sqlite3`.

Each successfully delivered formal Telegram betting alert is recorded as a simulated trade. No-opportunity notifications are not trades. After settlement, the system calculates hit rate, P&L, equity, and maximum drawdown.

```bash
python3 polymarket_trade_backtest.py all \
  --db work/polymarket_snapshots.sqlite3 --bankroll 10
```

Reports are written to `outputs/polymarket_trade_backtest.json` and `outputs/polymarket_trade_backtest_trades.csv`.

The Ubuntu deployment captures snapshots every 30 minutes and refreshes resolutions and the rolling backtest daily at 18:10.

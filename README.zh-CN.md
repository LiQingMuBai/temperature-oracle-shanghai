# 上海市最高气温量化决策系统

[English](README.md) | **简体中文**

Ubuntu服务器部署参见 [DEPLOY_UBUNTU.md](DEPLOY_UBUNTU.md)。

这是一个零第三方依赖、可审计的系统：预测上海次日最高气温，将天气概率与Polymarket实时订单簿结合，并通过Telegram发送经过风险过滤的信号。系统不会自动执行真实交易。

## Weather Underground / ZSPD回测

```bash
python3 wu_backtest.py download --start-year 2015
python3 wu_backtest.py backtest --start-year 2020
```

数据保存在 `data/wu_zspd_daily_c.csv`；报告与逐日预测写入 `outputs/`。整数温度档模型采用嵌套滚动验证，报告命中率、对数损失和多分类Brier分数。

## 历史数值天气预报回测

```bash
python3 nwp_backtest.py download --start 2024-01-01
python3 nwp_backtest.py backtest
python3 enhanced_nwp.py download --start 2024-01-01
python3 enhanced_nwp.py backtest
```

系统使用Open-Meteo Previous Runs API的固定D+1/D+2留档预报，对比GFS、ECMWF、CMA、JMA及滚动偏差校正集合。增强版加入露点、云量、短波辐射、降水、风矢量和高温交互项。

## 快速运行

```bash
python3 app.py update --start 2010-01-01
python3 app.py backtest --start-year 2018 --threshold 35
python3 app.py forecast --threshold 35
python3 polymarket_analysis.py
```

## 回测定义

- 目标：只使用目标日前可获得的数据预测次日最高气温。
- 切分：扩展窗口逐日回测，不随机打散。
- 对照：昨日最高温和季节气候基线。
- 指标：MAE、RMSE、偏差、±2°C命中率、整数档命中率、Brier分数和对数损失。

## Telegram Polymarket信号

监控器按上海时区自动选择次日市场，扫描相邻双档和三档组合。正式下注通知必须同时满足：

- 模型组合概率至少50%；
- 组合包含模型最高概率温度档；
- 至少3个原始天气模式支持组合；
- 每个档位成交价至少1¢；
- 模型组合概率减去可成交总成本后的净优势至少10%；
- 同一日期合约的累计风险不超过当前权益的20%。

历史偏差校准相对当日原始多模式中心最多移动±1°C。策略按真实订单簿深度计算等份订单，不会自动下单。

配置步骤：

1. 使用 `@BotFather` 创建Telegram机器人并获得Token。
2. 将 `telegram.env.example` 复制为 `work/telegram.env`，填写Token和Chat ID。
3. 运行只读演练：

```bash
python3 telegram_polymarket_monitor.py --dry-run
```

正式检查：

```bash
python3 telegram_polymarket_monitor.py --env-file work/telegram.env
```

有机会时通知下注清单、限价、资金占比和最大亏损；无机会时每6小时最多发送一次状态通知。相同信号会去重。

## 资金管理

默认初始资金为10美元：

- 已结算盈亏计入权益；
- 未结算模拟仓位占用现金；
- 同一合约风险上限为权益的20%；
- 默认每档10份，预算不足时自动缩减；
- 少于最低5份仍无法成交时拒绝信号。

## 实时快照与交易级滚动回测

每次正式监控都会将当时的模型、概率、逐档盘口、完整卖盘深度、候选组合和过滤结果写入 `work/polymarket_snapshots.sqlite3`。

每次Telegram正式下注通知发送成功后，会被记录为一笔模拟真实成交；无机会通知不计入交易。合约结算后自动计算命中率、盈亏、累计权益和最大回撤。

```bash
python3 polymarket_trade_backtest.py all \
  --db work/polymarket_snapshots.sqlite3 --bankroll 10
```

报告写入 `outputs/polymarket_trade_backtest.json` 和 `outputs/polymarket_trade_backtest_trades.csv`。

Ubuntu服务器默认每30分钟采集一次快照，每天18:10更新结算和滚动回测。

## 距离结算时间分层

生产任务同时监控今日和次日合约，依据Polymarket官方事件 `endDate` 计算剩余时间，划分为24h、12h、6h和3h档。默认“最低概率/最低优势”分别为50%/10%、52%/8%、55%/6%和60%/5%。滚动报告会分别统计各档的命中率、盈亏和平均入场优势。

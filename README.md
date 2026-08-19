# 上海市最高气温量化决策系统

Ubuntu 服务器部署参见 [`DEPLOY_UBUNTU.md`](DEPLOY_UBUNTU.md)。

这是一个零第三方依赖、可审计的 MVP：预测上海中心城区次日最高气温，并将预测映射为高温资源调度信号。默认使用 Open-Meteo 历史再分析和实时数值预报；正式业务应替换为上海市气象局站点实况与留档预报。

## Weather Underground / ZSPD 回测版

按 Weather Underground 月度历史页下载浦东机场站每日最高/最低温（摄氏度），再进行无未来泄漏的滚动回测：

```bash
python3 wu_backtest.py download --start-year 2015
python3 wu_backtest.py backtest --start-year 2020
```

数据保存在 `data/wu_zspd_daily_c.csv`；回测报告和逐日预测分别为 `outputs/wu_zspd_backtest_report.json`、`outputs/wu_zspd_backtest_predictions.csv`。

整数温度档模型使用嵌套滚动验证，动态校准“岭回归概率分布 + 昨日温度概率分布”的权重和宽度；报告整数档命中率、对数损失与多分类 Brier 分数。

## 历史数值天气预报回测

```bash
python3 nwp_backtest.py download --start 2024-01-01
python3 nwp_backtest.py backtest
```

使用 Open-Meteo Previous Runs API 的固定 D+1/D+2 留档预报，比较 GFS、ECMWF、CMA、JMA、原始等权集合及滚动偏差校正的动态集合。

增强版加入D+1留档的露点、白天云量、短波辐射、降水及风矢量，并含高温交互项：

```bash
python3 enhanced_nwp.py download --start 2024-01-01
python3 enhanced_nwp.py backtest
```

回测还包含在线元模型：在最多240天的过去窗口中查找季节和预报温度相近的天气，动态选择原集合与增强模型的融合权重。

## 快速运行

```bash
python3 app.py update --start 2010-01-01
python3 app.py backtest --start-year 2018 --threshold 35
python3 app.py forecast --threshold 35
python3 polymarket_analysis.py
```

产物写入 `outputs/`：`backtest_report.json`、`backtest_predictions.csv` 和 `latest_forecast.json`。
Polymarket 融合分析另写入 `outputs/polymarket_shanghai_jul31.json`，包含逐档盘口、$100 买入 VWAP、多模式机场预报、公平概率与可成交价差。

## 回测定义

- 目标：用目标日前已有数据预测次日最高气温。
- 切分：扩展窗口逐日回测，每 30 天只用此前数据重训；不随机打散。
- 对照：昨日最高温（持续性基线）和仅使用历年同期数据的季节气候基线。
- 指标：MAE、RMSE、系统偏差、±2°C 命中率、≥35°C 高温召回率；另评估 33°C 黄色信号对 35°C 高温事件的召回率、精确率和误报率。
- 模型：季节周期 + 1/2/7 日滞后 + 7/30 日均值 + 短期趋势的岭回归。

## 决策规则

阈值默认 35°C，可由业务改为自己的设备、客流或能耗阈值。33–35°C 为黄色准备，35–37°C 为橙色执行，≥37°C 为红色应急。实时结果融合 75% 数值天气预报和 25% 统计模型。±2°C 是风险带，并非经过概率校准的置信区间。

## 生产化建议

以 16 区自动站数据替代中心点；每日保存“当时发布的预报”以做真实逐提前期回测；增加湿度、城市热岛、云量和副热带高压特征；按成本函数优化阈值，并设置数据缺失、模型漂移和连续高温告警。

## Telegram Polymarket 信号

监控器自动选择上海时区的次日市场，扫描相邻双档和三档组合。只有同时满足三项硬条件才通知：模型组合概率不低于 50%、组合包含模型最高概率温度档、模型组合概率减去订单簿实际成交成本后的净优势不低于 10%（不扣手续费）。默认以每档 10 份检查盘口深度，不会自动下单。

额外稳健性过滤：历史偏差校准相对当日原始多模式中心最多移动 ±1°C；至少 3 个原始天气模式的整数预测落入候选组合；任何买入档低于 1¢ 时不发信号，避免廉价尾部概率制造虚假优势。

1. 在 Telegram 的 `@BotFather` 创建机器人并取得 Token；给机器人发送一条消息，再通过 Telegram Bot API 的 `getUpdates` 取得数字 `chat_id`。
2. 复制 `telegram.env.example` 为 `work/telegram.env`，填入 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID`。该文件已加入 `.gitignore`。
3. 先做只读演练：

```bash
python3 telegram_polymarket_monitor.py --dry-run
```

配置完成后可手工验证一次通知逻辑：

```bash
python3 telegram_polymarket_monitor.py --env-file work/telegram.env
```

相同组合不会反复通知；只有首次触发、最佳组合变化，或净优势比上次通知再提高至少 2 个百分点时才会重发。运行状态保存在 `work/telegram_monitor_state.json`。

通知还会列出每个温度档应买的 YES 份数、依据当前深度计算的最高限价、预计买入总成本和执行纪律。只有全部档位仍能在通知限价内成交时才执行；任一档价格变贵就放弃该组信号，避免残腿和追价。

默认资金规模为 10 美元。通知会同时显示本次投入占资产比例、保留现金、最坏亏损，以及任一所选温度档命中时的预计回款和毛利润。可通过 `POLYMARKET_BANKROLL_USD` 修改资金规模。

没有组合通过全部规则时，系统也会发送 Telegram 状态通知，列出最接近的组合和未通过原因。为避免每30分钟刷屏，无机会通知默认每6小时最多一次；从有机会切换为无机会时会立即通知。

## 实时快照与交易级滚动回测

每次正式监控会把当时的模型预报、概率中心、逐档买卖盘、完整卖盘深度、全部候选组合和过滤结果写入 `work/polymarket_snapshots.sqlite3`。快照只追加，不使用事后价格覆盖历史。

每次正式Telegram下注通知成功送达后，系统立即将该通知记为一笔模拟真实成交；通知几次就记录几笔，无机会状态通知不记交易。成交档位、份数、当时盘口成本、概率和资金规模都会被冻结保存。结算后计算命中率、盈亏、累计权益和最大回撤。手工更新结算并生成报告：

资金账本以10美元为初始权益：已结算盈亏计入权益，所有未结算模拟仓位占用现金。同一日期合约累计投入默认不超过当前权益的20%；10份超过预算时自动缩小等份订单，少于最低5份仍无法成交则拒绝信号。

```bash
python3 polymarket_trade_backtest.py all \
  --db work/polymarket_snapshots.sqlite3 --bankroll 10
```

结果写入 `outputs/polymarket_trade_backtest.json` 和 `outputs/polymarket_trade_backtest_trades.csv`。Ubuntu服务器另有每日18:10运行的 `shanghai-polymarket-backtest.timer`。

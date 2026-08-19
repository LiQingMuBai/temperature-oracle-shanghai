# Ubuntu 部署指南

本文将上海最高温 Polymarket 监控器部署到 Ubuntu，并通过 systemd 每 30 分钟运行一次。程序按 `Asia/Shanghai` 判断日期，自动查询次日市场；满足全部量化过滤条件时才发送 Telegram，不会自动下单。

## 1. 服务器要求

- Ubuntu 22.04 或更新版本
- Python 3.9+
- `curl`、`tzdata`
- 可访问 Open-Meteo、Polymarket Gamma/CLOB API 和 Telegram Bot API
- 建议至少 1 GB 内存、1 GB 可用磁盘

安装系统依赖：

```bash
sudo apt update
sudo apt install -y python3 curl tzdata rsync
```

可选：将服务器系统时区设为上海。程序本身已固定使用上海时区，因此这不是硬性要求。

```bash
sudo timedatectl set-timezone Asia/Shanghai
timedatectl
```

## 2. 创建独立运行用户

不要使用 root 长期运行监控器：

```bash
sudo useradd --system --create-home --home-dir /opt/shanghai-temperature \
  --shell /usr/sbin/nologin shanghaiwx
sudo mkdir -p /opt/shanghai-temperature/{work,outputs,data}
sudo chown -R shanghaiwx:shanghaiwx /opt/shanghai-temperature
```

## 3. 上传项目

在本地电脑的项目目录执行，将 `SERVER_IP` 和 `ubuntu` 替换为服务器信息：

```bash
rsync -av --delete \
  --exclude 'work/telegram.env' \
  --exclude 'work/telegram_monitor_state.json' \
  ./ ubuntu@SERVER_IP:/tmp/shanghai-temperature/
```

登录服务器并安装到正式目录：

```bash
ssh ubuntu@SERVER_IP
sudo rsync -a --delete /tmp/shanghai-temperature/ /opt/shanghai-temperature/
sudo mkdir -p /opt/shanghai-temperature/{work,outputs,data}
sudo chown -R shanghaiwx:shanghaiwx /opt/shanghai-temperature
```

注意：后续更新使用 `--delete` 时，必须继续排除服务器上的 `work/telegram.env` 和状态文件，避免删除密钥和去重状态。

## 4. 配置 Telegram

由于旧 Token 曾出现在聊天中，部署前应在 `@BotFather` 撤销旧 Token 并生成新的 Token。先在 Telegram 中打开机器人、解除屏蔽并发送 `/start`。

在服务器创建配置文件：

```bash
sudo -u shanghaiwx cp /opt/shanghai-temperature/telegram.env.example \
  /opt/shanghai-temperature/work/telegram.env
sudo -u shanghaiwx nano /opt/shanghai-temperature/work/telegram.env
```

填写配置：

```dotenv
TELEGRAM_BOT_TOKEN=新的机器人Token
TELEGRAM_CHAT_ID=数字ChatID
POLYMARKET_MIN_NET_EDGE=0.10
POLYMARKET_MIN_COMBO_PROBABILITY=0.50
POLYMARKET_MIN_MODEL_SUPPORT=3
POLYMARKET_MIN_LEG_PRICE=0.01
POLYMARKET_SHARES_PER_OUTCOME=10
POLYMARKET_BANKROLL_USD=10
```

限制文件权限：

```bash
sudo chown shanghaiwx:shanghaiwx /opt/shanghai-temperature/work/telegram.env
sudo chmod 600 /opt/shanghai-temperature/work/telegram.env
```

不要将此文件提交到 Git、发送到聊天或写入日志。

## 5. 首次手工测试

先进行只读演练，不发送 Telegram：

```bash
sudo -u shanghaiwx /usr/bin/python3 \
  /opt/shanghai-temperature/telegram_polymarket_monitor.py \
  --env-file /opt/shanghai-temperature/work/telegram.env \
  --dry-run
```

确认输出中的日期为上海时间的次日，并检查：

- `minimum_combo_probability` 为 `0.5`
- `minimum_model_support` 为 `3`
- `minimum_leg_price` 为 `0.01`
- 不合格组合的 `qualifies` 为 `false`

再执行一次正式检查。只有当前存在合格信号时才会发送 Telegram：

```bash
sudo -u shanghaiwx /usr/bin/python3 \
  /opt/shanghai-temperature/telegram_polymarket_monitor.py \
  --env-file /opt/shanghai-temperature/work/telegram.env
```

运行测试：

```bash
cd /opt/shanghai-temperature
sudo -u shanghaiwx python3 -m unittest -v test_telegram_polymarket_monitor.py
```

## 6. 创建 systemd 服务

创建 `/etc/systemd/system/shanghai-polymarket.service`：

```ini
[Unit]
Description=Shanghai temperature Polymarket monitor
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=shanghaiwx
Group=shanghaiwx
WorkingDirectory=/opt/shanghai-temperature
ExecStart=/usr/bin/python3 /opt/shanghai-temperature/telegram_polymarket_monitor.py --env-file /opt/shanghai-temperature/work/telegram.env
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/opt/shanghai-temperature/work /opt/shanghai-temperature/outputs

[Install]
WantedBy=multi-user.target
```

可用以下命令直接编辑：

```bash
sudo nano /etc/systemd/system/shanghai-polymarket.service
```

## 7. 创建每30分钟定时器

创建 `/etc/systemd/system/shanghai-polymarket.timer`：

```ini
[Unit]
Description=Run Shanghai Polymarket monitor every 30 minutes

[Timer]
OnCalendar=*-*-* *:00,30:00
Persistent=true
RandomizedDelaySec=20
Unit=shanghai-polymarket.service

[Install]
WantedBy=timers.target
```

加载并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now shanghai-polymarket.timer
sudo systemctl start shanghai-polymarket.service
```

确认定时器：

```bash
systemctl status shanghai-polymarket.timer --no-pager
systemctl list-timers shanghai-polymarket.timer --all
```

## 8. 查看运行日志

查看最近一次运行：

```bash
systemctl status shanghai-polymarket.service --no-pager
```

查看最近 100 行日志：

```bash
sudo journalctl -u shanghai-polymarket.service -n 100 --no-pager
```

持续查看：

```bash
sudo journalctl -u shanghai-polymarket.service -f
```

查看滚动回测状态和报告：

```bash
systemctl status shanghai-polymarket-backtest.timer --no-pager
journalctl -u shanghai-polymarket-backtest.service -n 100 --no-pager
cat /usr/unitree/outputs/polymarket_trade_backtest.json
```

备份不可回看的实时快照数据库：

```bash
cp /usr/unitree/work/polymarket_snapshots.sqlite3 \
  /usr/unitree/work/polymarket_snapshots.$(date +%F).sqlite3
```

日志不应包含 Telegram Token。去重状态保存在：

```text
/opt/shanghai-temperature/work/telegram_monitor_state.json
```

## 9. 暂停、恢复和立即运行

暂停定时检查：

```bash
sudo systemctl disable --now shanghai-polymarket.timer
```

恢复：

```bash
sudo systemctl enable --now shanghai-polymarket.timer
```

立即检查一次：

```bash
sudo systemctl start shanghai-polymarket.service
```

## 10. 更新项目

先暂停任务，然后上传新版。不要覆盖密钥和状态文件：

```bash
sudo systemctl stop shanghai-polymarket.timer
sudo rsync -a --delete \
  --exclude 'work/telegram.env' \
  --exclude 'work/telegram_monitor_state.json' \
  /tmp/shanghai-temperature/ /opt/shanghai-temperature/
sudo chown -R shanghaiwx:shanghaiwx /opt/shanghai-temperature
cd /opt/shanghai-temperature
sudo -u shanghaiwx python3 -m unittest -v test_telegram_polymarket_monitor.py
sudo systemctl daemon-reload
sudo systemctl enable --now shanghai-polymarket.timer
```

## 11. 常见故障

### Telegram 返回 403

在 Telegram 中打开机器人，解除屏蔽，发送 `/start`。确认 Chat ID 属于与该机器人建立过会话的用户或群组。

### 找不到次日市场

Polymarket 可能尚未创建对应日期的市场。程序不会改查错误日期，等待下一次定时运行即可。

### 接口超时

确认服务器可访问：

```bash
curl -I https://api.open-meteo.com
curl -I https://gamma-api.polymarket.com
curl -I https://clob.polymarket.com
curl -I https://api.telegram.org
```

### 服务没有写入权限

```bash
sudo chown -R shanghaiwx:shanghaiwx \
  /opt/shanghai-temperature/work \
  /opt/shanghai-temperature/outputs
```

### 防止重复部署

部署到服务器后，建议暂停本机 Codex 中的同名定时任务，否则本机和服务器会同时查询；虽然状态去重各自独立，仍可能收到重复 Telegram 通知。

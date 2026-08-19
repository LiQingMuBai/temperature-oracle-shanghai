#!/usr/bin/env python3
"""Run the monitor for both today's and tomorrow's Shanghai contracts."""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def slug_for(day):
    return f"highest-temperature-in-shanghai-on-{day.strftime('%B').lower()}-{day.day}-{day.year}"


def load_env(path):
    if not path.exists(): return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line=raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key,value=line.split("=",1);os.environ.setdefault(key.strip(),value.strip().strip("'\""))


def telegram_health(message):
    token,chat_id=os.getenv("TELEGRAM_BOT_TOKEN"),os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id or os.getenv("POLYMARKET_HEALTH_NOTIFY","1") != "1": return
    data=urllib.parse.urlencode({"chat_id":chat_id,"text":message}).encode()
    request=urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",data=data,method="POST")
    with urllib.request.urlopen(request,timeout=20) as response:
        result=json.loads(response.read())
    if not result.get("ok"): raise RuntimeError("Telegram health notification failed")


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--env-file",type=Path,default=ROOT/"work"/"telegram.env")
    args=ap.parse_args();load_env(args.env_file)
    now=dt.datetime.now(ZoneInfo("Asia/Shanghai"));today=now.date()
    failed=False; statuses=[]
    for offset in (0,1):
        day=today+dt.timedelta(days=offset)
        command=[sys.executable,str(ROOT/"telegram_polymarket_monitor.py"),"--env-file",str(args.env_file),
                 "--date",day.isoformat(),"--slug",slug_for(day)]
        result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True)
        if result.stdout: print(result.stdout,end="")
        if result.stderr: print(result.stderr,end="",file=sys.stderr)
        failed = failed or result.returncode != 0
        statuses.append(("今日" if offset==0 else "次日",day.isoformat(),result.returncode==0))
    lines=["上海气温量化服务健康检查",f"时间：{now:%Y-%m-%d %H:%M:%S}（上海）"]
    lines += [f"{label}市场 {day}：{'正常' if ok else '失败'}" for label,day,ok in statuses]
    lines.append("整体状态：" + ("运行正常" if not failed else "存在故障，请检查服务器日志"))
    telegram_health("\n".join(lines))
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__": main()

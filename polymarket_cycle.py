#!/usr/bin/env python3
"""Run the monitor for both today's and tomorrow's Shanghai contracts."""
import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent


def slug_for(day):
    return f"highest-temperature-in-shanghai-on-{day.strftime('%B').lower()}-{day.day}-{day.year}"


def main():
    ap=argparse.ArgumentParser();ap.add_argument("--env-file",type=Path,default=ROOT/"work"/"telegram.env")
    args=ap.parse_args(); today=dt.datetime.now(ZoneInfo("Asia/Shanghai")).date()
    failed=False
    for offset in (0,1):
        day=today+dt.timedelta(days=offset)
        command=[sys.executable,str(ROOT/"telegram_polymarket_monitor.py"),"--env-file",str(args.env_file),
                 "--date",day.isoformat(),"--slug",slug_for(day)]
        result=subprocess.run(command,cwd=ROOT)
        failed = failed or result.returncode != 0
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__": main()

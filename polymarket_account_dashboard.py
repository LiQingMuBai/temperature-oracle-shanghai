#!/usr/bin/env python3
"""Responsive web dashboard for aggregated watched-account trades."""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from polymarket_account_db import dashboard_data


ROOT = Path(__file__).resolve().parent

HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Polymarket 账户交易雷达</title>
<style>
:root{color-scheme:dark;--bg:#07111f;--panel:#0d1b2d;--panel2:#12243a;--text:#edf6ff;--muted:#91a7bf;--line:#203751;--blue:#58a6ff;--green:#37d67a;--orange:#ffb84d;--red:#ff667a;--purple:#b995ff}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(circle at 15% -10%,#16375b 0,transparent 32%),var(--bg);color:var(--text);font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1320px;margin:auto;padding:28px 22px 56px}.top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:22px}.eyebrow{color:var(--blue);font-size:13px;letter-spacing:.12em;text-transform:uppercase}.title{font-size:30px;font-weight:700;margin:6px 0}.sub{color:var(--muted);font-size:14px}.status{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}.dot{width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 0 5px #37d67a20}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat{background:#0d1b2dcc;border:1px solid var(--line);border-radius:14px;padding:16px}.stat-label{color:var(--muted);font-size:13px}.stat-value{font-size:24px;font-weight:700;margin-top:7px;font-variant-numeric:tabular-nums}.stat small{color:var(--muted)}
.controls{display:grid;grid-template-columns:180px minmax(220px,1fr) 170px;gap:10px;margin:18px 0}.control{width:100%;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:11px 12px;font:inherit;outline:none}.control:focus{border-color:var(--blue);box-shadow:0 0 0 3px #58a6ff24}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:0 0 14px}.legend span{display:flex;align-items:center;gap:7px}.swatch{width:10px;height:10px;border-radius:3px}.swatch.large{background:var(--green)}.swatch.medium{background:var(--orange)}.swatch.small{background:var(--blue)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.trade{position:relative;background:linear-gradient(145deg,#0e1e31,#0b1828);border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:14px;padding:16px;overflow:hidden}.trade.large{border-left-color:var(--green);background:linear-gradient(145deg,#0d2824,#0b1a28)}.trade.medium{border-left-color:var(--orange);background:linear-gradient(145deg,#292417,#0b1928)}.trade.repeated:after{content:"重复买入";position:absolute;right:12px;top:12px;color:var(--purple);background:#b995ff17;border:1px solid #b995ff45;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700}
.head{padding-right:88px}.account{color:var(--blue);font-size:12px;font-weight:700}.market{font-size:16px;font-weight:650;line-height:1.45;margin:5px 0}.outcome{display:inline-flex;background:#ffffff0b;border:1px solid var(--line);border-radius:999px;padding:4px 9px;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:15px;padding-top:13px;border-top:1px solid var(--line)}.metric b{display:block;font-size:16px;font-variant-numeric:tabular-nums}.metric span{color:var(--muted);font-size:11px}.buy b{color:var(--green)}.sell b{color:var(--red)}.footer{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:13px;color:var(--muted);font-size:12px}.footer a{color:var(--blue);text-decoration:none}.empty,.error{grid-column:1/-1;text-align:center;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:42px;color:var(--muted)}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:620px){.wrap{padding:20px 14px 40px}.top{display:block}.status{margin-top:14px}.title{font-size:24px}.controls{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.footer{align-items:flex-start;flex-direction:column}.stat-value{font-size:20px}}
</style>
</head>
<body><main class="wrap">
<header class="top"><div><div class="eyebrow">Live account intelligence</div><h1 class="title">Polymarket 账户交易雷达</h1><div class="sub">同一标的自动汇总 · 每分钟更新 · 仅统计监听开始后的成交</div></div><div class="status"><span class="dot"></span><span id="updated">正在加载</span></div></header>
<section class="stats" aria-label="汇总数据"><div class="stat"><div class="stat-label">累计买入</div><div class="stat-value" id="buy">—</div></div><div class="stat"><div class="stat-label">累计卖出</div><div class="stat-value" id="sell">—</div></div><div class="stat"><div class="stat-label">成交笔数</div><div class="stat-value" id="trades">—</div></div><div class="stat"><div class="stat-label">标的数量</div><div class="stat-value" id="targets">—</div></div></section>
<section class="controls" aria-label="筛选"><select class="control" id="account" aria-label="账户"><option value="all">全部账户</option></select><input class="control" id="search" type="search" placeholder="搜索市场或方向" aria-label="搜索"><select class="control" id="sort" aria-label="排序"><option value="latest">最近成交</option><option value="amount">买入金额</option><option value="repeats">重复次数</option></select></section>
<div class="legend"><span><i class="swatch large"></i>累计买入 ≥ $100</span><span><i class="swatch medium"></i>$50–$99.99</span><span><i class="swatch small"></i>&lt; $50</span></div>
<section class="grid" id="grid" aria-live="polite"><div class="empty">正在读取交易数据…</div></section>
</main>
<script>
const $=id=>document.getElementById(id);let groups=[];const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const num=n=>Number(n||0).toLocaleString('en-US',{maximumFractionDigits:2});const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function time(ts){return new Intl.DateTimeFormat('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(ts*1000))}
function render(){let rows=[...groups],mode=$('sort').value;if(mode==='amount')rows.sort((a,b)=>b.buy_usdc-a.buy_usdc);else if(mode==='repeats')rows.sort((a,b)=>b.buy_count-a.buy_count);else rows.sort((a,b)=>b.last_timestamp-a.last_timestamp);$('grid').innerHTML=rows.length?rows.map(x=>`<article class="trade ${x.size_tier} ${x.is_repeated?'repeated':''}"><div class="head"><div class="account">@${esc(x.account_name)}</div><div class="market">${esc(x.title)}</div><span class="outcome">${esc(x.outcome)}</span></div><div class="metrics"><div class="metric buy"><b>${money(x.buy_usdc)}</b><span>累计买入 · ${x.buy_count}笔</span></div><div class="metric sell"><b>${money(x.sell_usdc)}</b><span>累计卖出 · ${x.sell_count}笔</span></div><div class="metric"><b>${num(x.net_size)}</b><span>净持有份数</span></div><div class="metric"><b>${(x.avg_buy_price*100).toFixed(1)}¢</b><span>平均买入价</span></div></div><div class="footer"><span>最近成交 ${time(x.last_timestamp)}</span><a href="https://polymarket.com/event/${encodeURIComponent(x.event_slug||x.market_slug)}" target="_blank" rel="noopener">打开市场 ↗</a></div></article>`).join(''):'<div class="empty">当前筛选条件下没有成交</div>'}
async function load(){let p=new URLSearchParams({account:$('account').value,q:$('search').value});try{let r=await fetch('/api/data?'+p);if(!r.ok)throw Error('HTTP '+r.status);let d=await r.json();groups=d.groups;$('buy').textContent=money(d.totals.buy_usdc);$('sell').textContent=money(d.totals.sell_usdc);$('trades').textContent=num(d.totals.trades);$('targets').textContent=num(d.totals.targets);$('updated').textContent='更新于 '+time(d.generated_at);let current=$('account').value;if($('account').options.length===1){d.accounts.forEach(a=>$('account').add(new Option('@'+a,a)));$('account').value=current}render()}catch(e){$('grid').innerHTML='<div class="error">数据加载失败：'+esc(e.message)+'</div>';}}
$('account').addEventListener('change',load);let timer;$('search').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)});$('sort').addEventListener('change',render);load();setInterval(load,60000);
</script></body></html>'''


class Handler(BaseHTTPRequestHandler):
    db_path = None

    def send_bytes(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/":
            return self.send_bytes(200, "text/html; charset=utf-8", HTML.encode())
        if parsed.path == "/healthz":
            return self.send_bytes(200, "text/plain; charset=utf-8", b"ok\n")
        if parsed.path == "/api/data":
            params = parse_qs(parsed.query)
            account = params.get("account", ["all"])[0][:64]
            query = params.get("q", [""])[0][:100]
            try:
                payload = dashboard_data(self.db_path, account=account, query=query)
                body = json.dumps(payload, ensure_ascii=False).encode()
                return self.send_bytes(200, "application/json; charset=utf-8", body)
            except Exception as exc:
                body = json.dumps({"error": str(exc)}, ensure_ascii=False).encode()
                return self.send_bytes(500, "application/json; charset=utf-8", body)
        self.send_bytes(404, "text/plain; charset=utf-8", b"not found\n")

    def log_message(self, fmt, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=ROOT / "work" / "polymarket_account_watch.sqlite3")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8766)
    args = parser.parse_args()
    Handler.db_path = args.db
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"account dashboard listening on http://{args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

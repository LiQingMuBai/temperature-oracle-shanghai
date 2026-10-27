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
.wrap{max-width:1320px;margin:auto;padding:28px 22px 56px}.top{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;margin-bottom:22px}.eyebrow{color:var(--blue);font-size:13px;letter-spacing:.12em;text-transform:uppercase}.title{font-size:30px;font-weight:700;margin:6px 0}.sub{color:var(--muted);font-size:14px}.status-wrap{display:flex;align-items:center;gap:12px;flex-wrap:wrap;justify-content:flex-end}.status{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}.dot{width:9px;height:9px;border-radius:50%;background:var(--green);box-shadow:0 0 0 5px #37d67a20}.lang{background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:9px;padding:8px 10px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}.stat{background:#0d1b2dcc;border:1px solid var(--line);border-radius:14px;padding:16px}.stat-label{color:var(--muted);font-size:13px}.stat-value{font-size:24px;font-weight:700;margin-top:7px;font-variant-numeric:tabular-nums}.stat small{color:var(--muted)}
.controls{display:grid;grid-template-columns:180px minmax(220px,1fr) 170px;gap:10px;margin:18px 0}.control{width:100%;background:var(--panel);color:var(--text);border:1px solid var(--line);border-radius:10px;padding:11px 12px;font:inherit;outline:none}.control:focus{border-color:var(--blue);box-shadow:0 0 0 3px #58a6ff24}
.legend{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin:0 0 14px}.legend span{display:flex;align-items:center;gap:7px}.swatch{width:10px;height:10px;border-radius:3px}.swatch.large{background:var(--green)}.swatch.medium{background:var(--orange)}.swatch.small{background:var(--blue)}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.trade{position:relative;background:linear-gradient(145deg,#0e1e31,#0b1828);border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:14px;padding:16px;overflow:hidden}.trade.large{border-left-color:var(--green);background:linear-gradient(145deg,#0d2824,#0b1a28)}.trade.medium{border-left-color:var(--orange);background:linear-gradient(145deg,#292417,#0b1928)}.trade.repeated:after{content:attr(data-repeat-label);position:absolute;right:12px;top:12px;color:var(--purple);background:#b995ff17;border:1px solid #b995ff45;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700}
.head{padding-right:88px}.account{color:var(--blue);font-size:12px;font-weight:700}.market{font-size:16px;font-weight:650;line-height:1.45;margin:5px 0}.outcome{display:inline-flex;background:#ffffff0b;border:1px solid var(--line);border-radius:999px;padding:4px 9px;font-size:12px}.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:15px;padding-top:13px;border-top:1px solid var(--line)}.metric b{display:block;font-size:16px;font-variant-numeric:tabular-nums}.metric span{color:var(--muted);font-size:11px}.buy b{color:var(--green)}.sell b{color:var(--red)}.footer{display:flex;justify-content:space-between;gap:12px;align-items:center;margin-top:13px;color:var(--muted);font-size:12px}.footer a{color:var(--blue);text-decoration:none}.empty,.error{grid-column:1/-1;text-align:center;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:42px;color:var(--muted)}
@media(max-width:900px){.stats{grid-template-columns:repeat(2,1fr)}.grid{grid-template-columns:1fr}}@media(max-width:620px){.wrap{padding:20px 14px 40px}.top{display:block}.status{margin-top:14px}.title{font-size:24px}.controls{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.footer{align-items:flex-start;flex-direction:column}.stat-value{font-size:20px}}
</style>
</head>
<body><main class="wrap">
<header class="top"><div><div class="eyebrow">Live account intelligence</div><h1 class="title" data-i18n="title">Polymarket 账户交易雷达</h1><div class="sub" data-i18n="subtitle">同一标的自动汇总 · 每分钟更新 · 仅统计监听开始后的成交</div></div><div class="status-wrap"><div class="status"><span class="dot"></span><span id="updated" data-i18n="loading">正在加载</span></div><select id="language" class="lang" aria-label="Language"><option value="zh">中文</option><option value="en">English</option></select></div></header>
<section class="stats"><div class="stat"><div class="stat-label" data-i18n="totalBuy">累计买入</div><div class="stat-value" id="buy">—</div></div><div class="stat"><div class="stat-label" data-i18n="totalSell">累计卖出</div><div class="stat-value" id="sell">—</div></div><div class="stat"><div class="stat-label" data-i18n="tradeCount">成交笔数</div><div class="stat-value" id="trades">—</div></div><div class="stat"><div class="stat-label" data-i18n="targetCount">标的数量</div><div class="stat-value" id="targets">—</div></div></section>
<section class="controls"><select class="control" id="account"><option value="all" data-i18n="allAccounts">全部账户</option></select><input class="control" id="search" type="search" placeholder="搜索市场或方向"><select class="control" id="sort"><option value="latest" data-i18n="latest">最近成交</option><option value="amount" data-i18n="buyAmount">买入金额</option><option value="repeats" data-i18n="repeatCount">重复次数</option></select></section>
<div class="legend"><span><i class="swatch large"></i><span data-i18n="largeLegend">累计买入 ≥ $100</span></span><span><i class="swatch medium"></i><span data-i18n="mediumLegend">$50–$99.99</span></span><span><i class="swatch small"></i><span data-i18n="smallLegend">&lt; $50</span></span></div>
<section class="grid" id="grid" aria-live="polite"><div class="empty" data-i18n="reading">正在读取交易数据…</div></section>
</main>
<script>
const $=id=>document.getElementById(id);let groups=[],lang=localStorage.getItem('watch-language')||'zh';
const copy={zh:{title:'Polymarket 账户交易雷达',subtitle:'同一标的自动汇总 · 每分钟更新 · 仅统计监听开始后的成交',loading:'正在加载',totalBuy:'累计买入',totalSell:'累计卖出',tradeCount:'成交笔数',targetCount:'标的数量',allAccounts:'全部账户',latest:'最近成交',buyAmount:'买入金额',repeatCount:'重复次数',largeLegend:'累计买入 ≥ $100',mediumLegend:'$50–$99.99',smallLegend:'< $50',reading:'正在读取交易数据…',search:'搜索市场或方向',repeated:'重复买入',buy:'累计买入',sell:'累计卖出',trades:'笔',netShares:'净持有份数',avgBuy:'平均买入价',lastTrade:'最近成交',openMarket:'打开市场 ↗',empty:'当前筛选条件下没有成交',updated:'更新于',error:'数据加载失败：'},en:{title:'Polymarket Account Trade Radar',subtitle:'Repeated fills aggregated · Updated every minute · Trades since monitoring began',loading:'Loading',totalBuy:'Total buys',totalSell:'Total sells',tradeCount:'Trades',targetCount:'Markets',allAccounts:'All accounts',latest:'Latest trade',buyAmount:'Buy amount',repeatCount:'Repeat count',largeLegend:'Cumulative buys ≥ $100',mediumLegend:'$50–$99.99',smallLegend:'< $50',reading:'Loading trade data…',search:'Search market or outcome',repeated:'Repeated buys',buy:'Total bought',sell:'Total sold',trades:'trades',netShares:'Net shares',avgBuy:'Average buy price',lastTrade:'Last trade',openMarket:'Open market ↗',empty:'No trades match these filters',updated:'Updated',error:'Unable to load data: '}};const t=k=>copy[lang][k];
const money=n=>'$'+Number(n||0).toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2});const num=n=>Number(n||0).toLocaleString('en-US',{maximumFractionDigits:2});const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function time(ts){return new Intl.DateTimeFormat(lang==='zh'?'zh-CN':'en-US',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(ts*1000))}
function applyLanguage(){document.documentElement.lang=lang==='zh'?'zh-CN':'en';document.title=t('title');document.querySelectorAll('[data-i18n]').forEach(el=>el.textContent=t(el.dataset.i18n));$('search').placeholder=t('search');$('language').value=lang;render()}
function render(){let rows=[...groups],mode=$('sort').value;if(mode==='amount')rows.sort((a,b)=>b.buy_usdc-a.buy_usdc);else if(mode==='repeats')rows.sort((a,b)=>b.buy_count-a.buy_count);else rows.sort((a,b)=>b.last_timestamp-a.last_timestamp);$('grid').innerHTML=rows.length?rows.map(x=>`<article class="trade ${x.size_tier} ${x.is_repeated?'repeated':''}" ${x.is_repeated?`data-repeat-label="${t('repeated')}"`:''}><div class="head"><div class="account">@${esc(x.account_name)}</div><div class="market">${esc(x.title)}</div><span class="outcome">${esc(x.outcome)}</span></div><div class="metrics"><div class="metric buy"><b>${money(x.buy_usdc)}</b><span>${t('buy')} · ${x.buy_count} ${t('trades')}</span></div><div class="metric sell"><b>${money(x.sell_usdc)}</b><span>${t('sell')} · ${x.sell_count} ${t('trades')}</span></div><div class="metric"><b>${num(x.net_size)}</b><span>${t('netShares')}</span></div><div class="metric"><b>${(x.avg_buy_price*100).toFixed(1)}¢</b><span>${t('avgBuy')}</span></div></div><div class="footer"><span>${t('lastTrade')} ${time(x.last_timestamp)}</span><a href="https://polymarket.com/event/${encodeURIComponent(x.event_slug||x.market_slug)}" target="_blank" rel="noopener">${t('openMarket')}</a></div></article>`).join(''):`<div class="empty">${t('empty')}</div>`}
async function load(){let p=new URLSearchParams({account:$('account').value,q:$('search').value});try{let r=await fetch('/api/data?'+p);if(!r.ok)throw Error('HTTP '+r.status);let d=await r.json();groups=d.groups;$('buy').textContent=money(d.totals.buy_usdc);$('sell').textContent=money(d.totals.sell_usdc);$('trades').textContent=num(d.totals.trades);$('targets').textContent=num(d.totals.targets);$('updated').textContent=t('updated')+' '+time(d.generated_at);let current=$('account').value;if($('account').options.length===1){d.accounts.forEach(a=>$('account').add(new Option('@'+a,a)));$('account').value=current}render()}catch(e){$('grid').innerHTML=`<div class="error">${t('error')}${esc(e.message)}</div>`;}}
$('account').addEventListener('change',load);let timer;$('search').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(load,250)});$('sort').addEventListener('change',render);$('language').addEventListener('change',e=>{lang=e.target.value;localStorage.setItem('watch-language',lang);applyLanguage();load()});applyLanguage();load();setInterval(load,60000);
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

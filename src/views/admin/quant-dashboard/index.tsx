import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Clock3, CopyCheck, Radio, Search, Terminal, WalletCards } from 'lucide-react'

type Language = 'en' | 'zh'
type TradeGroup = { account_name:string; token_id:string; title:string; outcome:string; event_slug:string; market_slug:string; buy_usdc:number; sell_usdc:number; buy_count:number; sell_count:number; net_size:number; avg_buy_price:number; last_timestamp:number; is_repeated:boolean }
type Payload = { generated_at:number; accounts:string[]; totals:{buy_usdc:number;sell_usdc:number;trades:number;targets:number}; groups:TradeGroup[] }
const empty:Payload={generated_at:0,accounts:[],totals:{buy_usdc:0,sell_usdc:0,trades:0,targets:0},groups:[]}
const copy={
  en:{eyebrow:'WATCHED WALLET INTELLIGENCE',title:'WALLET TRACE // POLYMARKET',sub:'Tracked wallets only · Repeated fills aggregated · Duplicate buys highlighted',live:'LIVE · 15S POLL',offline:'OFFLINE',buyTotal:'TOTAL BUY VALUE',sellTotal:'TOTAL SELL VALUE',trades:'TRACKED TRADES',repeatedTargets:'REPEATED TARGETS',all:'ALL WATCHED WALLETS',search:'SEARCH MARKET OR OUTCOME',repeat:'REPEAT',buyValue:'BUY VALUE',sellValue:'SELL VALUE',buys:'BUYS',sells:'SELLS',net:'NET SHARES',avg:'AVG BUY PRICE',open:'OPEN MARKET ↗',empty:'NO MATCHING TRADES',legend:'GREEN ≥ $100 · AMBER $50–99.99 · BLUE < $50',updated:'LAST SYNC'},
  zh:{eyebrow:'关注地址情报终端',title:'地址追踪 // POLYMARKET',sub:'仅展示关注地址 · 重复成交自动汇总 · 重复购买醒目标识',live:'在线 · 15秒轮询',offline:'离线',buyTotal:'累计购买价值',sellTotal:'累计卖出价值',trades:'关注地址成交',repeatedTargets:'重复购买标的',all:'全部关注地址',search:'搜索市场或方向',repeat:'重复',buyValue:'购买价值',sellValue:'卖出价值',buys:'笔购买',sells:'笔卖出',net:'净持有份数',avg:'平均买入价',open:'打开市场 ↗',empty:'当前筛选条件下没有成交',legend:'绿色 ≥ $100 · 橙色 $50–99.99 · 蓝色 < $50',updated:'最后同步'},
}
const money=(v:number)=>v.toLocaleString('en-US',{style:'currency',currency:'USD',minimumFractionDigits:2})
const num=(v:number)=>v.toLocaleString('en-US',{maximumFractionDigits:2})
const tone=(v:number)=>v>=100?'border-[#00ff88]/45 bg-[#00ff88]/10 text-[#66ffad]':v>=50?'border-amber-400/40 bg-amber-400/10 text-amber-300':'border-cyan-400/35 bg-cyan-400/10 text-cyan-300'

export default function QuantDashboard(){
  const [data,setData]=useState<Payload>(empty),[account,setAccount]=useState('all'),[query,setQuery]=useState(''),[connected,setConnected]=useState(false),[error,setError]=useState('')
  const [language,setLanguage]=useState<Language>(()=>(localStorage.getItem('wallet-language') as Language)||'en')
  const t=copy[language]
  const stamp=(ts:number)=>new Intl.DateTimeFormat(language==='zh'?'zh-CN':'en-GB',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date(ts*1000))
  const refresh=useCallback(async()=>{try{const r=await fetch(`/api/data?${new URLSearchParams({account,q:query})}`,{cache:'no-store'});if(!r.ok)throw Error(`HTTP ${r.status}`);setData(await r.json() as Payload);setConnected(true);setError('')}catch(e){setConnected(false);setError(e instanceof Error?e.message:'UNKNOWN')}},[account,query])
  useEffect(()=>{refresh();const id=window.setInterval(refresh,15000);return()=>window.clearInterval(id)},[refresh])
  useEffect(()=>{localStorage.setItem('wallet-language',language);document.documentElement.lang=language==='zh'?'zh-CN':'en';document.title=language==='zh'?'关注地址交易雷达':'Wallet Trace // Polymarket'},[language])
  const repeated=useMemo(()=>data.groups.filter(x=>x.is_repeated).length,[data.groups])
  return <main className="hacker-shell mx-auto min-h-screen max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8">
    <header className="mb-6 flex flex-col gap-4 border-b border-[#00ff88]/20 pb-6 lg:flex-row lg:items-end lg:justify-between">
      <div><div className="mb-2 flex items-center gap-2 text-xs font-bold tracking-[.24em] text-[#00ff88]"><Terminal size={14}/>{t.eyebrow}</div><h1 className="glitch-title text-2xl font-black tracking-tight text-white sm:text-3xl">{t.title}</h1><p className="mt-2 text-sm text-[#719081]">{t.sub}</p></div>
      <div className="flex items-center gap-2"><div className={`inline-flex items-center gap-2 rounded border px-3 py-2 text-xs ${connected?'border-[#00ff88]/40 bg-[#00ff88]/10 text-[#00ff88]':'border-rose-400/40 bg-rose-400/10 text-rose-300'}`}><Radio size={13}/>{connected?t.live:`${t.offline} ${error}`}</div><button onClick={()=>setLanguage(language==='en'?'zh':'en')} className="rounded border border-[#00ff88]/35 bg-black px-3 py-2 text-xs font-bold text-[#00ff88] transition hover:bg-[#00ff88]/10">{language==='en'?'中文':'EN'}</button></div>
    </header>
    <section className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {[[t.buyTotal,money(data.totals.buy_usdc),'text-[#00ff88]'],[t.sellTotal,money(data.totals.sell_usdc),'text-rose-400'],[t.trades,num(data.totals.trades),'text-white'],[t.repeatedTargets,num(repeated),'text-fuchsia-300']].map(([label,value,color])=><div key={label} className="hacker-panel p-4"><p className="text-[11px] tracking-[.14em] text-[#60796d]">&gt; {label}</p><p className={`mt-2 text-2xl font-black ${color}`}>{value}</p></div>)}
    </section>
    <div className="hacker-panel mb-5 grid gap-3 p-4 lg:grid-cols-[230px_1fr_auto] lg:items-center">
      <select value={account} onChange={e=>setAccount(e.target.value)} className="terminal-input"><option value="all">{t.all}</option>{data.accounts.map(name=><option key={name} value={name}>@{name}</option>)}</select>
      <label className="terminal-input flex items-center gap-3"><Search size={15} className="text-[#00ff88]"/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder={t.search} className="w-full bg-transparent outline-none placeholder:text-[#3b5649]"/></label>
      <div className="flex gap-2 text-[10px]"><span className="rounded border border-[#00ff88]/35 px-2 py-1 text-[#00ff88]">≥$100</span><span className="rounded border border-amber-400/35 px-2 py-1 text-amber-300">$50–99</span><span className="rounded border border-cyan-400/35 px-2 py-1 text-cyan-300">&lt;$50</span></div>
    </div>
    <section className="grid gap-4 xl:grid-cols-2">{data.groups.map(row=><article key={`${row.account_name}:${row.token_id}`} className={`hacker-panel relative overflow-hidden p-5 ${row.is_repeated?'!border-fuchsia-400/50 shadow-[0_0_28px_rgba(232,121,249,.08)]':''}`}>
      {row.is_repeated&&<span className="absolute right-4 top-4 flex items-center gap-1 rounded border border-fuchsia-400/50 bg-fuchsia-400/10 px-2 py-1 text-[10px] font-black tracking-wider text-fuchsia-300"><CopyCheck size={12}/>{t.repeat}</span>}
      <div className="pr-24"><p className="text-xs font-bold text-[#00ff88]">root@poly:~/{row.account_name}</p><h2 className="mt-2 line-clamp-2 min-h-12 text-base font-bold leading-6 text-[#d7ffe7]">{row.title}</h2><span className="mt-2 inline-flex rounded border border-[#00ff88]/20 bg-black/60 px-2 py-1 text-xs text-[#8bb89d]">[{row.outcome}]</span></div>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4"><div className={`rounded border p-3 ${tone(row.buy_usdc)}`}><p className="flex items-center gap-1 text-[9px] tracking-wider opacity-75"><ArrowUpRight size={11}/>{t.buyValue}</p><b className="mt-1 block text-lg">{money(row.buy_usdc)}</b><small>{row.buy_count} {t.buys}</small></div><div className="rounded border border-rose-400/25 bg-rose-400/5 p-3 text-rose-300"><p className="flex items-center gap-1 text-[9px] tracking-wider opacity-75"><ArrowDownRight size={11}/>{t.sellValue}</p><b className="mt-1 block text-lg">{money(row.sell_usdc)}</b><small>{row.sell_count} {t.sells}</small></div><div className="metric-box"><small>{t.net}</small><b>{num(row.net_size)}</b></div><div className="metric-box"><small>{t.avg}</small><b>{(row.avg_buy_price*100).toFixed(1)}¢</b></div></div>
      <footer className="mt-4 flex items-center justify-between border-t border-[#00ff88]/10 pt-4 text-[11px] text-[#587063]"><span className="flex items-center gap-1"><Clock3 size={12}/>{stamp(row.last_timestamp)}</span><a className="text-[#00ff88] hover:text-white" href={`https://polymarket.com/event/${encodeURIComponent(row.event_slug||row.market_slug)}`} target="_blank" rel="noreferrer">{t.open}</a></footer>
    </article>)}</section>
    {!data.groups.length&&<div className="hacker-panel mt-4 py-16 text-center text-sm text-[#587063]">&gt; {t.empty}<span className="terminal-cursor">_</span></div>}
    <footer className="mt-6 flex justify-between gap-3 text-[10px] text-[#3f5f4e]"><span>{t.legend}</span><span>{t.updated}: {data.generated_at?stamp(data.generated_at):'—'}</span></footer>
  </main>
}

import { useCallback, useEffect, useMemo, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Clock3, CopyCheck, Radio, Search, WalletCards } from 'lucide-react'
import Card from '../../../components/quant/Card'

type TradeGroup = {
  account_name: string; token_id: string; title: string; outcome: string; event_slug: string; market_slug: string
  buy_usdc: number; sell_usdc: number; buy_count: number; sell_count: number; trade_count: number
  net_size: number; avg_buy_price: number; last_timestamp: number; is_repeated: boolean
}
type DashboardPayload = {
  generated_at: number; accounts: string[]
  totals: { buy_usdc: number; sell_usdc: number; trades: number; targets: number }
  groups: TradeGroup[]
}
const empty: DashboardPayload = { generated_at: 0, accounts: [], totals: { buy_usdc: 0, sell_usdc: 0, trades: 0, targets: 0 }, groups: [] }
const money = (value: number) => value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })
const number = (value: number) => value.toLocaleString('en-US', { maximumFractionDigits: 2 })
const time = (timestamp: number) => new Intl.DateTimeFormat('zh-CN', { timeZone: 'Asia/Shanghai', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }).format(new Date(timestamp * 1000))
const valueTone = (value: number) => value >= 100
  ? 'border-emerald-400/25 bg-emerald-400/10 text-emerald-300'
  : value >= 50 ? 'border-amber-400/25 bg-amber-400/10 text-amber-300' : 'border-sky-400/25 bg-sky-400/10 text-sky-300'

export default function QuantDashboard() {
  const [data, setData] = useState<DashboardPayload>(empty)
  const [account, setAccount] = useState('all')
  const [query, setQuery] = useState('')
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    try {
      const response = await fetch(`/api/data?${new URLSearchParams({ account, q: query })}`, { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setData(await response.json() as DashboardPayload); setConnected(true); setError('')
    } catch (reason) { setConnected(false); setError(reason instanceof Error ? reason.message : 'Unknown error') }
  }, [account, query])
  useEffect(() => { refresh(); const id = window.setInterval(refresh, 15_000); return () => window.clearInterval(id) }, [refresh])
  const repeated = useMemo(() => data.groups.filter((row) => row.is_repeated).length, [data.groups])

  return <main className="mx-auto min-h-screen max-w-[1500px] px-4 py-6 sm:px-6 lg:px-8">
    <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div><div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[.22em] text-violet-300"><WalletCards size={14} /> Watched wallet intelligence</div><h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">关注地址交易雷达</h1><p className="mt-2 text-sm text-slate-400">仅展示关注地址成交 · 同一标的自动汇总 · 重复购买醒目标识</p></div>
      <div className={`inline-flex w-fit items-center gap-2 rounded-full border px-3 py-2 text-xs ${connected ? 'border-emerald-400/25 bg-emerald-400/8 text-emerald-300' : 'border-rose-400/25 bg-rose-400/8 text-rose-300'}`}><Radio size={13} /> {connected ? 'LIVE · 每 15 秒刷新' : `OFFLINE · ${error}`}</div>
    </header>
    <section className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      <Card className="!p-4"><p className="text-xs text-slate-400">累计购买价值</p><p className="mt-2 text-2xl font-semibold text-emerald-300">{money(data.totals.buy_usdc)}</p></Card>
      <Card className="!p-4"><p className="text-xs text-slate-400">累计卖出价值</p><p className="mt-2 text-2xl font-semibold text-rose-300">{money(data.totals.sell_usdc)}</p></Card>
      <Card className="!p-4"><p className="text-xs text-slate-400">关注地址成交</p><p className="mt-2 text-2xl font-semibold text-white">{number(data.totals.trades)} 笔</p></Card>
      <Card className="!p-4"><p className="text-xs text-slate-400">重复购买标的</p><p className="mt-2 text-2xl font-semibold text-violet-300">{number(repeated)} 个</p></Card>
    </section>
    <Card className="mb-5 !p-4"><div className="grid gap-3 lg:grid-cols-[220px_1fr_auto] lg:items-center">
      <select value={account} onChange={(event) => setAccount(event.target.value)} className="rounded-xl border border-white/10 bg-[#0b1020] px-4 py-3 text-sm text-slate-200 outline-none focus:border-violet-400/50"><option value="all">全部关注地址</option>{data.accounts.map((name) => <option key={name} value={name}>@{name}</option>)}</select>
      <label className="flex items-center gap-3 rounded-xl border border-white/10 bg-[#0b1020] px-4 py-3 focus-within:border-violet-400/50"><Search size={16} className="text-slate-500" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索市场或购买方向" className="w-full bg-transparent text-sm text-white outline-none placeholder:text-slate-600" /></label>
      <div className="flex flex-wrap gap-2 text-[11px]"><span className="rounded-full border border-emerald-400/25 bg-emerald-400/10 px-3 py-1.5 text-emerald-300">≥ $100</span><span className="rounded-full border border-amber-400/25 bg-amber-400/10 px-3 py-1.5 text-amber-300">$50–99.99</span><span className="rounded-full border border-sky-400/25 bg-sky-400/10 px-3 py-1.5 text-sky-300">&lt; $50</span></div>
    </div></Card>
    <section className="grid gap-4 xl:grid-cols-2">{data.groups.map((row) => <article key={`${row.account_name}:${row.token_id}`} className={`relative overflow-hidden rounded-[20px] border bg-[#101629]/92 p-5 shadow-[0_24px_80px_rgba(0,0,0,.2)] ${row.is_repeated ? 'border-violet-400/35' : 'border-white/8'}`}>
      {row.is_repeated && <span className="absolute right-4 top-4 inline-flex items-center gap-1.5 rounded-full border border-violet-400/35 bg-violet-400/15 px-3 py-1 text-[11px] font-bold text-violet-200"><CopyCheck size={13} />重复</span>}
      <div className="pr-24"><p className="text-xs font-semibold text-violet-300">@{row.account_name}</p><h2 className="mt-2 line-clamp-2 min-h-12 text-base font-semibold leading-6 text-white">{row.title}</h2><span className="mt-2 inline-flex rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-xs text-slate-300">{row.outcome}</span></div>
      <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className={`rounded-xl border p-3 ${valueTone(row.buy_usdc)}`}><div className="flex items-center gap-1 text-[10px] uppercase opacity-70"><ArrowUpRight size={12} />购买价值</div><strong className="mt-1 block text-lg tabular-nums">{money(row.buy_usdc)}</strong><span className="text-[10px] opacity-70">{row.buy_count} 笔购买</span></div>
        <div className="rounded-xl border border-rose-400/15 bg-rose-400/5 p-3 text-rose-300"><div className="flex items-center gap-1 text-[10px] uppercase opacity-70"><ArrowDownRight size={12} />卖出价值</div><strong className="mt-1 block text-lg tabular-nums">{money(row.sell_usdc)}</strong><span className="text-[10px] opacity-70">{row.sell_count} 笔卖出</span></div>
        <div className="rounded-xl border border-white/8 bg-white/[.025] p-3"><div className="text-[10px] uppercase text-slate-500">净持有份数</div><strong className="mt-1 block text-lg tabular-nums text-slate-200">{number(row.net_size)}</strong></div>
        <div className="rounded-xl border border-white/8 bg-white/[.025] p-3"><div className="text-[10px] uppercase text-slate-500">平均买入价</div><strong className="mt-1 block text-lg tabular-nums text-slate-200">{(row.avg_buy_price * 100).toFixed(1)}¢</strong></div>
      </div>
      <footer className="mt-4 flex items-center justify-between gap-3 border-t border-white/6 pt-4 text-xs text-slate-500"><span className="flex items-center gap-1.5"><Clock3 size={13} />{time(row.last_timestamp)}</span><a className="text-sky-400 transition hover:text-sky-300" href={`https://polymarket.com/event/${encodeURIComponent(row.event_slug || row.market_slug)}`} target="_blank" rel="noreferrer">打开市场 ↗</a></footer>
    </article>)}</section>
    {!data.groups.length && <Card className="mt-4 py-16 text-center text-sm text-slate-500">当前筛选条件下没有成交记录</Card>}
    <footer className="mt-6 flex flex-wrap justify-between gap-2 text-[11px] text-slate-600"><span>绿色 ≥ $100 · 橙色 $50–99.99 · 蓝色 &lt; $50</span><span>更新于 {data.generated_at ? time(data.generated_at) : '—'}</span></footer>
  </main>
}

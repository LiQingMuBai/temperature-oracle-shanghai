import { useCallback, useEffect, useState } from 'react'
import { Activity, CircleDollarSign, Fuel, Radio, ShieldCheck, WalletCards } from 'lucide-react'
import ComplexTable from '../../../components/quant/ComplexTable'
import DepthAreaChart from '../../../components/quant/DepthAreaChart'
import MiniStatistics from '../../../components/quant/MiniStatistics'
import ProbabilityLineChart from '../../../components/quant/ProbabilityLineChart'
import type { QuantPayload } from '../../../types/quant'

const empty: QuantPayload = {
  generatedAt: 0,
  selectedEvent: { title: 'Waiting for live market data', outcome: 'YES', eventSlug: '' },
  metrics: { pnl: 0, exposure: 0, activeArbitrage: 0, gasFeePol: null },
  probability: [], depth: [], arbitrage: [], trackedAccounts: [], dataMode: 'LIVE_WITH_MODEL_REFERENCE',
}

const usd = (value: number) => value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })

export default function QuantDashboard() {
  const [data, setData] = useState<QuantPayload>(empty)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/quant', { cache: 'no-store' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setData(await response.json() as QuantPayload)
      setConnected(true); setError('')
    } catch (reason) {
      setConnected(false); setError(reason instanceof Error ? reason.message : 'Unknown error')
    }
  }, [])

  useEffect(() => { refresh(); const id = window.setInterval(refresh, 2000); return () => window.clearInterval(id) }, [refresh])

  return (
    <main className="mx-auto min-h-screen max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8">
      <header className="mb-6 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div><div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[.22em] text-violet-300"><Activity size={14} /> Quant intelligence</div><h1 className="text-2xl font-semibold tracking-tight text-white sm:text-3xl">Polymarket Quant Terminal</h1><p className="mt-2 max-w-3xl text-sm text-slate-400">Tracked accounts, probability microstructure, executable depth and model-reference premium flow.</p></div>
        <div className="flex flex-wrap items-center gap-2 text-xs"><span className={`inline-flex items-center gap-2 rounded-full border px-3 py-2 ${connected ? 'border-emerald-400/25 bg-emerald-400/8 text-emerald-300' : 'border-rose-400/25 bg-rose-400/8 text-rose-300'}`}><Radio size={13} />{connected ? 'LIVE · 2s' : `OFFLINE · ${error}`}</span><span className="rounded-full border border-white/8 bg-white/4 px-3 py-2 text-slate-400">{data.trackedAccounts.map((x) => `@${x}`).join(' · ') || 'Loading accounts'}</span></div>
      </header>
      <section className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <MiniStatistics name="账户当前 P&L / Account P&L" value={usd(data.metrics.pnl)} detail="Open-position cash P&L" icon={CircleDollarSign} tone="emerald" />
        <MiniStatistics name="总风险敞口 / Exposure" value={usd(data.metrics.exposure)} detail="Current marked position value" icon={WalletCards} tone="violet" />
        <MiniStatistics name="活跃套利 / Active arbitrage" value={String(data.metrics.activeArbitrage)} detail="Model-reference gap ≥ 2%" icon={ShieldCheck} tone="cyan" />
        <MiniStatistics name="链上 Gas / Polygon Gas" value={data.metrics.gasFeePol == null ? '—' : `${data.metrics.gasFeePol.toFixed(5)} POL`} detail="Estimated 200k gas transaction" icon={Fuel} tone="amber" />
      </section>
      <section className="grid gap-5 xl:grid-cols-2">
        <ProbabilityLineChart title={`${data.selectedEvent.title} · ${data.selectedEvent.outcome}`} points={data.probability} />
        <DepthAreaChart points={data.depth} />
      </section>
      <section className="mt-5"><ComplexTable rows={data.arbitrage} /></section>
      <footer className="mt-5 flex flex-wrap justify-between gap-2 text-[11px] text-slate-500"><span>Live Polymarket market data · Model reference is clearly separated from exchange quotes.</span><span>Updated {data.generatedAt ? new Date(data.generatedAt * 1000).toLocaleTimeString('zh-CN', { hour12: false }) : '—'}</span></footer>
    </main>
  )
}

import { memo } from 'react'
import type { ArbitrageRow } from '../../types/quant'
import Card from './Card'

const money = (value: number) => `$${value.toLocaleString('en-US', { maximumFractionDigits: 0 })}`

function ComplexTable({ rows }: { rows: ArbitrageRow[] }) {
  return (
    <Card title="实时套利流 / Live Arbitrage Stream" subtitle="Polymarket live price vs model reference · reference is not a live Kalshi quote">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] border-separate border-spacing-0 text-left text-sm">
          <thead><tr className="text-[11px] uppercase tracking-wider text-slate-500">
            <th className="border-b border-white/8 px-3 py-3">Market</th><th className="border-b border-white/8 px-3 py-3">Outcome</th><th className="border-b border-white/8 px-3 py-3 text-right">Polymarket</th><th className="border-b border-white/8 px-3 py-3 text-right">Model ref.</th><th className="border-b border-white/8 px-3 py-3 text-right">Premium</th><th className="border-b border-white/8 px-3 py-3 text-right">Flow</th><th className="border-b border-white/8 px-3 py-3 text-right">Signal</th>
          </tr></thead>
          <tbody>{rows.map((row) => {
            const positive = row.premium >= 0
            return <tr key={row.id} className={`border-b border-white/5 ${positive ? 'flash-positive' : 'flash-negative'}`}>
              <td className="max-w-[360px] truncate px-3 py-3.5 font-medium text-slate-200">{row.market}</td>
              <td className="px-3 py-3.5 text-slate-400">{row.outcome}</td>
              <td className="px-3 py-3.5 text-right tabular-nums text-white">{(row.polymarket * 100).toFixed(1)}¢</td>
              <td className="px-3 py-3.5 text-right tabular-nums text-slate-300">{(row.reference * 100).toFixed(1)}¢</td>
              <td className={`px-3 py-3.5 text-right font-semibold tabular-nums ${positive ? 'text-emerald-400' : 'text-rose-400'}`}>{positive ? '+' : ''}{(row.premium * 100).toFixed(2)}%</td>
              <td className="px-3 py-3.5 text-right tabular-nums text-slate-300">{money(row.volume)}</td>
              <td className="px-3 py-3.5 text-right"><span className={`rounded-full px-2.5 py-1 text-[10px] font-bold tracking-wide ${row.signal === 'BUY_POLY' ? 'bg-emerald-400/12 text-emerald-300' : row.signal === 'SELL_POLY' ? 'bg-rose-400/12 text-rose-300' : 'bg-slate-400/10 text-slate-400'}`}>{row.signal.replace('_', ' ')}</span></td>
            </tr>
          })}</tbody>
        </table>
      </div>
    </Card>
  )
}

export default memo(ComplexTable)

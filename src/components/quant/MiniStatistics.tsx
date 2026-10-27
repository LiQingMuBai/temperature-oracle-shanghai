import type { LucideIcon } from 'lucide-react'
import Card from './Card'

type Props = {
  name: string
  value: string
  detail: string
  icon: LucideIcon
  tone?: 'violet' | 'cyan' | 'emerald' | 'amber'
}

const tones = {
  violet: 'from-violet-500/25 text-violet-300 ring-violet-400/25',
  cyan: 'from-cyan-500/25 text-cyan-300 ring-cyan-400/25',
  emerald: 'from-emerald-500/25 text-emerald-300 ring-emerald-400/25',
  amber: 'from-amber-500/25 text-amber-300 ring-amber-400/25',
}

export default function MiniStatistics({ name, value, detail, icon: Icon, tone = 'violet' }: Props) {
  return (
    <Card className="flex min-h-28 items-center gap-4 !p-4">
      <div className={`grid size-12 shrink-0 place-items-center rounded-2xl bg-gradient-to-br to-transparent ring-1 ${tones[tone]}`}>
        <Icon size={21} aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <p className="truncate text-xs text-slate-400">{name}</p>
        <p className="mt-1 truncate text-2xl font-semibold tracking-tight text-white tabular-nums">{value}</p>
        <p className="mt-1 truncate text-[11px] text-slate-500">{detail}</p>
      </div>
    </Card>
  )
}

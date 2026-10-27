import type { PropsWithChildren, ReactNode } from 'react'

type CardProps = PropsWithChildren<{
  title?: string
  subtitle?: string
  action?: ReactNode
  className?: string
}>

export default function Card({ title, subtitle, action, className = '', children }: CardProps) {
  return (
    <section className={`rounded-[20px] border border-white/8 bg-[#101629]/92 p-5 shadow-[0_24px_80px_rgba(0,0,0,.25)] backdrop-blur ${className}`}>
      {(title || action) && (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-base font-semibold tracking-tight text-white">{title}</h2>}
            {subtitle && <p className="mt-1 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      {children}
    </section>
  )
}

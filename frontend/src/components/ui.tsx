// Small shadcn-style component set (hand-written, Tailwind + Radix primitives).
import * as SliderPrimitive from '@radix-ui/react-slider'
import * as TooltipPrimitive from '@radix-ui/react-tooltip'
import { animate, useMotionValue, useTransform, motion } from 'framer-motion'
import { AlertTriangle, Inbox, Loader2 } from 'lucide-react'
import { useEffect, type ButtonHTMLAttributes, type ReactNode } from 'react'
import { cn, STATUS_COLOUR, STATUS_LABEL } from '../lib/utils'

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn('glass rounded-2xl', className)} {...rest}>{children}</div>
}

export function CardTitle({ children, icon, right }: { children: ReactNode; icon?: ReactNode; right?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-5 pt-4 pb-2">
      <h3 className="flex min-w-0 items-center gap-2 text-sm font-semibold tracking-wide text-muted uppercase">{icon}{children}</h3>
      {right}
    </div>
  )
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'ghost' | 'outline' | 'danger'; loading?: boolean }
export function Button({ className, variant = 'primary', loading, children, disabled, ...rest }: BtnProps) {
  const styles = {
    primary: 'bg-accent text-accent-fg hover:brightness-110 glow',
    ghost: 'hover:bg-panel-2 text-fg',
    outline: 'border border-line hover:bg-panel-2 text-fg',
    danger: 'bg-bad/90 text-white hover:bg-bad',
  }[variant]
  return (
    <button
      className={cn('inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50', styles, className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  )
}

export function StatusBadge({ status }: { status: string }) {
  const c = STATUS_COLOUR[status] ?? '#8b93a3'
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap"
      style={{ background: `${c}1f`, color: c, border: `1px solid ${c}55` }}>
      <span className="size-1.5 rounded-full" style={{ background: c }} />
      {STATUS_LABEL[status] ?? status}
    </span>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn('animate-pulse rounded-xl bg-panel-2', className)} />
}

export function Empty({ title, children, icon }: { title: string; children?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 px-6 py-14 text-center">
      <div className="rounded-2xl border border-line bg-panel-2 p-4 text-muted">{icon ?? <Inbox className="size-7" />}</div>
      <p className="font-medium">{title}</p>
      {children && <div className="max-w-md text-sm text-muted">{children}</div>}
    </div>
  )
}

export function ErrorState({ error }: { error: unknown }) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-bad/40 bg-bad/10 p-4 text-sm">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-bad" />
      <span>{error instanceof Error ? error.message : 'Something went wrong.'}</span>
    </div>
  )
}

export function Slider({ value, min, max, step, onChange, label, format }: {
  value: number; min: number; max: number; step: number; onChange: (v: number) => void; label: string; format?: (v: number) => string
}) {
  return (
    <label className="block">
      <div className="mb-2 flex justify-between text-xs text-muted"><span>{label}</span><span className="font-mono text-fg">{format ? format(value) : value}</span></div>
      <SliderPrimitive.Root className="relative flex h-6 w-full touch-none items-center select-none" value={[value]} min={min} max={max} step={step}
        onValueChange={(v) => onChange(v[0])} aria-label={label}>
        <SliderPrimitive.Track className="relative h-1.5 grow rounded-full bg-panel-2">
          <SliderPrimitive.Range className="absolute h-full rounded-full bg-accent" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb className="block size-5 rounded-full border-2 border-accent bg-bg shadow glow" />
      </SliderPrimitive.Root>
    </label>
  )
}

export function Tip({ children, content }: { children: ReactNode; content: ReactNode }) {
  return (
    <TooltipPrimitive.Root delayDuration={200}>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content sideOffset={6} className="z-50 max-w-xs rounded-xl border border-line bg-[#0d1117] px-3 py-2 text-xs leading-relaxed text-[#e6e9ef] shadow-xl">
          {content}
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  )
}

/** Animates from 0 up to a value that came from the API. */
export function CountUp({ value, decimals = 0, suffix = '' }: { value: number | null | undefined; decimals?: number; suffix?: string }) {
  const mv = useMotionValue(0)
  const text = useTransform(mv, (v) => `${v.toFixed(decimals)}${suffix}`)
  useEffect(() => {
    if (value === null || value === undefined) return
    const c = animate(mv, value, { duration: 0.9, ease: 'easeOut' })
    return () => c.stop()
  }, [value, mv])
  if (value === null || value === undefined) return <span className="text-muted">—</span>
  return <motion.span>{text}</motion.span>
}

export function ConfBar({ value, label }: { value: number | null | undefined; label: string }) {
  const v = value ?? 0
  const c = v >= 0.75 ? '#34d399' : v >= 0.45 ? '#fbbf24' : '#f87171'
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs text-muted"><span>{label}</span><span className="font-mono text-fg">{value === null || value === undefined ? '—' : `${(v * 100).toFixed(0)}%`}</span></div>
      <div className="h-1.5 overflow-hidden rounded-full bg-panel-2">
        <motion.div className="h-full rounded-full" style={{ background: c }} initial={{ width: 0 }} animate={{ width: `${v * 100}%` }} transition={{ duration: 0.6 }} />
      </div>
    </div>
  )
}

export function Kpi({ label, value, decimals, suffix, icon, hint }: { label: string; value: number | null | undefined; decimals?: number; suffix?: string; icon: ReactNode; hint?: string }) {
  return (
    <Card className="p-5">
      <div className="flex items-center justify-between text-muted"><span className="text-xs tracking-wide uppercase">{label}</span>{icon}</div>
      <div className="mt-3 text-3xl font-semibold tabular-nums"><CountUp value={value} decimals={decimals} suffix={suffix} /></div>
      {hint && <div className="mt-1 text-xs text-muted">{hint}</div>}
    </Card>
  )
}

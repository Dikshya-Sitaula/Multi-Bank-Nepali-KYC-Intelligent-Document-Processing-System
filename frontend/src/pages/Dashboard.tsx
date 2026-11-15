import { useQuery } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import { CheckCircle2, Clock, FileStack, Gauge, ListChecks, Upload } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Area, AreaChart, Cell, Pie, PieChart, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts'
import { Button, Card, CardTitle, Empty, ErrorState, Kpi, Skeleton, StatusBadge } from '../components/ui'
import { api, type DocSummary } from '../lib/api'
import { STATUS_COLOUR, STATUS_LABEL } from '../lib/utils'

type Dash = {
  documents_total: number; documents_by_status: Record<string, number>; fields_by_status: Record<string, number>
  fields_total: number; avg_ocr_confidence: number | null; avg_processing_seconds: number | null
  per_template: { template_id: string; bank_name: string; documents: number }[]
  uploads_per_day: { date: string; documents: number }[]; recent: DocSummary[]
}

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({ queryKey: ['dashboard'], queryFn: () => api<Dash>('/dashboard'), refetchInterval: 5000 })
  if (isLoading) return <div className="grid gap-4 md:grid-cols-3">{[...Array(6)].map((_, i) => <Skeleton key={i} className="h-32" />)}</div>
  if (error) return <ErrorState error={error} />
  const d = data!
  const fieldPie = Object.entries(d.fields_by_status).filter(([, v]) => v > 0).map(([k, v]) => ({ name: STATUS_LABEL[k] ?? k, key: k, value: v }))
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h1 className="text-2xl font-semibold">Dashboard</h1><p className="text-sm text-muted">Live counts from the database.</p></div>
        <Link to="/upload"><Button><Upload className="size-4" />Upload a form</Button></Link>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <Kpi label="Documents" value={d.documents_total} icon={<FileStack className="size-4" />} />
        <Kpi label="Need review" value={d.documents_by_status.needs_review} icon={<ListChecks className="size-4" />} />
        <Kpi label="Verified" value={d.documents_by_status.verified} icon={<CheckCircle2 className="size-4" />} />
        <Kpi label="Fields extracted" value={d.fields_total} icon={<Gauge className="size-4" />} />
        <Kpi label="Avg OCR confidence" value={d.avg_ocr_confidence === null ? null : d.avg_ocr_confidence * 100} decimals={1} suffix="%" icon={<Gauge className="size-4" />} />
        <Kpi label="Avg processing" value={d.avg_processing_seconds} decimals={1} suffix=" s" icon={<Clock className="size-4" />} />
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Uploads, last 14 days</CardTitle>
          <div className="h-56 px-2 pb-4">
            <ResponsiveContainer>
              <AreaChart data={d.uploads_per_day}>
                <XAxis dataKey="date" tickFormatter={(v: string) => v.slice(5)} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                <YAxis allowDecimals={false} width={32} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
                <RTooltip contentStyle={{ background: '#0d1117', border: '1px solid #222', borderRadius: 12 }} />
                <Area dataKey="documents" stroke="#22d3ee" fill="#22d3ee30" strokeWidth={2} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
        <Card>
          <CardTitle>Field status</CardTitle>
          {fieldPie.length ? (
            <div className="h-56">
              <ResponsiveContainer>
                <PieChart>
                  <Pie data={fieldPie} dataKey="value" innerRadius={55} outerRadius={85} paddingAngle={2}>
                    {fieldPie.map((p) => <Cell key={p.key} fill={STATUS_COLOUR[p.key]} />)}
                  </Pie>
                  <RTooltip contentStyle={{ background: '#0d1117', border: '1px solid #222', borderRadius: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : <Empty title="No fields yet" />}
        </Card>
      </div>
      <div className="grid gap-5 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardTitle>Recent documents</CardTitle>
          {d.recent.length ? (
            <ul className="divide-y divide-line px-2 pb-2">
              {d.recent.map((r, i) => (
                <motion.li key={r.id} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}>
                  <Link to={`/documents/${r.id}`} className="flex min-h-14 items-center gap-3 rounded-xl px-3 hover:bg-panel-2">
                    <span className="min-w-0 flex-1 truncate">{r.display_name}</span>
                    <span className="hidden text-xs text-muted sm:inline">{r.bank_name ?? '—'}</span>
                    <StatusBadge status={r.status} />
                  </Link>
                </motion.li>
              ))}
            </ul>
          ) : <Empty title="No documents yet">Upload a form to see it here.</Empty>}
        </Card>
        <Card>
          <CardTitle>Documents per bank form</CardTitle>
          <div className="space-y-3 px-5 pb-5">
            {d.per_template.length ? d.per_template.map((t) => (
              <div key={t.template_id}>
                <div className="mb-1 flex justify-between text-sm"><span>{t.bank_name}</span><span className="font-mono">{t.documents}</span></div>
                <div className="h-1.5 rounded-full bg-panel-2"><motion.div className="h-full rounded-full bg-accent" initial={{ width: 0 }} animate={{ width: `${(t.documents / Math.max(1, d.documents_total)) * 100}%` }} /></div>
              </div>
            )) : <p className="text-sm text-muted">0 identified documents.</p>}
          </div>
        </Card>
      </div>
    </div>
  )
}

// VISION LAB: every stage of the real OpenCV pipeline for one page, with the image it
// produced, its parameters, metrics and timing. Sliders re-run the parameterised stages on
// the server (POST /documents/:id/pages/:n/lab); nothing here is simulated.
import { useMutation, useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { FlaskConical, Info, Layers, RotateCcw, SlidersHorizontal, Timer, Zap } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip as RTooltip, XAxis, YAxis } from 'recharts'
import { Button, Card, CardTitle, ConfBar, Empty, ErrorState, Skeleton, StatusBadge, Tip } from '../components/ui'
import { api, fileUrl, type DocDetail, type DocSummary, type Paged, type Stage, type StageRun } from '../lib/api'
import { cn, ms, pct } from '../lib/utils'

type Params = {
  denoise_method: string; denoise_strength: number; clahe_clip: number; clahe_tile: number
  threshold_method: string; threshold_block: number; threshold_c: number; canny_low: number; canny_high: number; matcher: string
}

function DocPicker() {
  const nav = useNavigate()
  const { data, isLoading, error } = useQuery({ queryKey: ['docs', 'lab'], queryFn: () => api<Paged<DocSummary>>('/documents?page_size=24') })
  if (isLoading) return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>
  if (error) return <ErrorState error={error} />
  const docs = (data?.items ?? []).filter((d) => d.status !== 'uploaded')
  if (!docs.length) return <Card><Empty title="No processed documents yet" icon={<FlaskConical className="size-7" />}>Upload a form first; every pipeline stage of it will appear here. <Link className="text-accent" to="/upload">Go to Upload</Link></Empty></Card>
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {docs.map((d) => (
        <button key={d.id} onClick={() => nav(`/lab/${d.id}`)} className="glass min-h-11 rounded-2xl p-4 text-left transition hover:glow">
          <div className="flex items-center justify-between gap-2"><span className="truncate font-medium">{d.display_name}</span><StatusBadge status={d.status} /></div>
          <div className="mt-2 text-xs text-muted">{d.bank_name ?? 'Unidentified'} · {d.page_count} page(s)</div>
        </button>
      ))}
    </div>
  )
}

function CompareView({ before, after, label }: { before?: string; after?: string; label: string }) {
  const [pos, setPos] = useState(50)
  if (!before || !after) return null
  return (
    <div>
      <div className="relative overflow-hidden rounded-xl border border-line bg-black/40">
        <img src={after} alt="after" className="block w-full select-none" draggable={false} />
        <div className="absolute inset-0" style={{ clipPath: `inset(0 ${100 - pos}% 0 0)` }}>
          <img src={before} alt="before" className="block w-full select-none" draggable={false} />
        </div>
        <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-accent glow" style={{ left: `${pos}%` }} />
        <span className="absolute top-2 left-2 rounded-md bg-black/60 px-2 py-0.5 text-xs text-white">before</span>
        <span className="absolute top-2 right-2 rounded-md bg-black/60 px-2 py-0.5 text-xs text-white">{label}</span>
      </div>
      <input type="range" min={0} max={100} value={pos} onChange={(e) => setPos(+e.target.value)} aria-label="Before/after position"
        className="mt-3 h-11 w-full accent-[var(--accent)]" />
    </div>
  )
}

function BlendView({ aligned, template }: { aligned?: string; template?: string }) {
  const [a, setA] = useState(0.55)
  if (!aligned || !template) return null
  return (
    <div>
      <div className="relative overflow-hidden rounded-xl border border-line bg-white">
        <img src={template} alt="blank template" className="block w-full" />
        <img src={aligned} alt="aligned page" className="absolute inset-0 w-full" style={{ opacity: a }} />
      </div>
      <label className="mt-3 block text-xs text-muted">Blend: blank template ← → aligned photo ({Math.round(a * 100)}%)
        <input type="range" min={0} max={1} step={0.01} value={a} onChange={(e) => setA(+e.target.value)} className="mt-1 h-11 w-full accent-[var(--accent)]" />
      </label>
    </div>
  )
}

function Metrics({ stage }: { stage: Stage }) {
  const entries = Object.entries(stage.metrics).filter(([, v]) => v !== null && typeof v !== 'object')
  const params = Object.entries(stage.params)
  return (
    <div className="space-y-3">
      {entries.length > 0 && (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          {entries.map(([k, v]) => (
            <div key={k} className="rounded-xl border border-line bg-panel-2 px-3 py-2">
              <dt className="truncate text-[11px] text-muted uppercase">{k.replace(/_/g, ' ')}</dt>
              <dd className="truncate font-mono">{typeof v === 'number' ? (Number.isInteger(v) ? v : v.toFixed(4)) : String(v)}</dd>
            </div>
          ))}
        </dl>
      )}
      {params.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {params.map(([k, v]) => <span key={k} className="rounded-lg border border-line px-2 py-1 font-mono text-[11px] text-muted">{k}={String(v)}</span>)}
        </div>
      )}
    </div>
  )
}

function StageExtras({ stage, all, doc, pageIndex }: { stage: Stage; all: Stage[]; doc: DocDetail; pageIndex: number }) {
  const d = stage.data as Record<string, unknown>
  if (stage.key === 'clahe' && Array.isArray(d.hist_before)) {
    const before = d.hist_before as number[]; const after = d.hist_after as number[]
    const rows = before.map((b, i) => ({ bin: i * 4, before: b, after: after[i] }))
    return (
      <div className="h-56">
        <ResponsiveContainer>
          <AreaChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid stroke="var(--line)" vertical={false} />
            <XAxis dataKey="bin" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
            <YAxis tick={{ fill: 'var(--muted)', fontSize: 11 }} width={48} />
            <RTooltip contentStyle={{ background: '#0d1117', border: '1px solid #222', borderRadius: 12 }} />
            <Area dataKey="before" stroke="#8b93a3" fill="#8b93a333" isAnimationActive />
            <Area dataKey="after" stroke="#22d3ee" fill="#22d3ee33" isAnimationActive />
          </AreaChart>
        </ResponsiveContainer>
        <p className="text-center text-xs text-muted">Grey-level histogram before (grey) and after (cyan) CLAHE</p>
      </div>
    )
  }
  if (stage.key === 'matching' && Array.isArray(d.candidates)) {
    const rows = (d.candidates as { template_id: string; page_number: number; inliers: number; good_matches: number }[])
      .slice().sort((a, b) => b.inliers - a.inliers).slice(0, 12)
      .map((c) => ({ name: `${c.template_id} p${c.page_number}`, inliers: c.inliers, good: c.good_matches }))
    return (
      <div style={{ height: Math.max(180, rows.length * 26) }}>
        <ResponsiveContainer>
          <BarChart data={rows} layout="vertical" margin={{ left: 8, right: 16 }}>
            <XAxis type="number" tick={{ fill: 'var(--muted)', fontSize: 11 }} />
            <YAxis type="category" dataKey="name" width={120} tick={{ fill: 'var(--muted)', fontSize: 11 }} />
            <RTooltip contentStyle={{ background: '#0d1117', border: '1px solid #222', borderRadius: 12 }} />
            <Bar dataKey="inliers" radius={[0, 6, 6, 0]}>
              {rows.map((r, i) => <Cell key={r.name} fill={i === 0 ? '#22d3ee' : '#334155'} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-center text-xs text-muted">RANSAC inliers against each enrolled template page (top 12)</p>
      </div>
    )
  }
  if (stage.key === 'alignment') {
    return <BlendView aligned={fileUrl(d.aligned_image as string)} template={fileUrl(d.template_image as string)} />
  }
  if (stage.key === 'snapping' && Array.isArray(d.boxes)) {
    const boxes = d.boxes as { region_id: string; snapped: boolean; iou_before: number; shift_px: number; printed_kind?: string }[]
    return (
      <div className="max-h-72 overflow-auto rounded-xl border border-line">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-bg/95 text-muted"><tr><th className="p-2 text-left">Region</th><th className="p-2 text-left">Snapped</th><th className="p-2 text-right">IoU</th><th className="p-2 text-right">Shift px</th></tr></thead>
          <tbody>
            {boxes.map((b) => (
              <tr key={b.region_id} className="border-t border-line">
                <td className="p-2 font-mono">{b.region_id}</td>
                <td className="p-2">{b.snapped ? <span className="text-good">to {b.printed_kind}</span> : <span className="text-muted">kept template box</span>}</td>
                <td className="p-2 text-right font-mono">{b.iou_before.toFixed(3)}</td>
                <td className="p-2 text-right font-mono">{b.shift_px.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }
  if (stage.key === 'crops' || stage.key === 'ocr' || stage.key === 'validation' || stage.key === 'checkboxes') {
    const page = doc.pages.find((p) => p.index === pageIndex)
    const fields = doc.fields.filter((f) => f.page_id === page?.id && f.crop_path && f.status !== 'empty')
    if (!fields.length) return <Empty title="No non-empty fields on this page" />
    return (
      <div className="grid max-h-[32rem] gap-3 overflow-auto sm:grid-cols-2">
        {fields.map((f, i) => (
          <motion.div key={f.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.6) }}
            className="rounded-xl border border-line bg-panel-2 p-3">
            <div className="mb-2 flex items-center justify-between gap-2"><span className="truncate text-xs font-medium">{f.display_name}{f.group_id ? ` · ${f.group_id}` : ''}</span><StatusBadge status={f.status} /></div>
            <img src={fileUrl(f.crop_path)} alt={f.display_name} className="max-h-20 w-full rounded-lg bg-white object-contain" loading="lazy" />
            {f.checkbox ? (
              <div className="mt-2 space-y-1 text-xs">
                {f.checkbox.map((o) => <div key={o.option_id} className="flex justify-between"><span>{o.option_id}</span><span className={cn('font-mono', o.state === 'selected' ? 'text-good' : o.state === 'ambiguous' ? 'text-warn' : 'text-muted')}>fill {o.fill_ratio.toFixed(2)} (base {o.baseline_ratio.toFixed(2)}) {o.state}</span></div>)}
              </div>
            ) : (
              <div className="mt-2 space-y-2">
                <div className={cn('truncate text-sm', /[ऀ-ॿ]/.test(f.raw_text ?? '') && 'devanagari')}>{f.raw_text ?? <span className="text-muted">— no text read —</span>}</div>
                <ConfBar value={f.ocr_confidence} label="OCR confidence" />
              </div>
            )}
          </motion.div>
        ))}
      </div>
    )
  }
  void all
  return null
}

export default function VisionLab() {
  const { id } = useParams()
  const [sp, setSp] = useSearchParams()
  const pageIndex = Number(sp.get('page') ?? 0)
  const docQ = useQuery({ queryKey: ['doc', id], queryFn: () => api<DocDetail>(`/documents/${id}`), enabled: !!id })
  const stagesQ = useQuery({ queryKey: ['stages', id, pageIndex], queryFn: () => api<StageRun>(`/documents/${id}/pages/${pageIndex}/stages`), enabled: !!id, retry: false })
  const [lab, setLab] = useState<StageRun | null>(null)
  const [selected, setSelected] = useState('original')
  const [params, setParams] = useState<Params | null>(null)
  useEffect(() => { setLab(null); setParams(null) }, [id, pageIndex])
  useEffect(() => { if (stagesQ.data && !params) setParams(stagesQ.data.params as Params) }, [stagesQ.data, params])

  const rerun = useMutation({
    mutationFn: (p: Params) => api<StageRun>(`/documents/${id}/pages/${pageIndex}/lab`, { method: 'POST', body: JSON.stringify(p) }),
    onSuccess: (r) => setLab(r),
  })
  // Debounced live re-run when a slider changes.
  useEffect(() => {
    if (!params || !stagesQ.data) return
    if (JSON.stringify(params) === JSON.stringify(stagesQ.data.params) && !lab) return
    const t = setTimeout(() => rerun.mutate(params), 600)
    return () => clearTimeout(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params])

  const saved = stagesQ.data?.stages ?? []
  const stages = useMemo(() => {
    if (!lab) return saved
    const byKey = new Map(lab.stages.map((s) => [s.key, s]))
    return saved.map((s) => byKey.get(s.key) ?? s)
  }, [saved, lab])
  const idx = Math.max(0, stages.findIndex((s) => s.key === selected))
  const stage = stages[idx]
  const prevWithImage = stages.slice(0, idx).reverse().find((s) => s.image)

  if (!id) {
    return (
      <div className="space-y-6">
        <Header />
        <DocPicker />
      </div>
    )
  }
  if (docQ.isLoading || stagesQ.isLoading) return <div className="space-y-4"><Header /><Skeleton className="h-24" /><Skeleton className="h-[60vh]" /></div>
  if (docQ.error) return <ErrorState error={docQ.error} />
  const doc = docQ.data!
  if (stagesQ.error) return <div className="space-y-4"><Header /><Card><Empty title="This page has not been processed yet">Processing runs in the background after upload; check the job tray at the top.</Empty></Card></div>

  const timing = stages.filter((s) => s.ms > 0).map((s) => ({ name: s.title, ms: s.ms, key: s.key }))
  const set = (k: keyof Params, v: Params[keyof Params]) => setParams((p) => (p ? { ...p, [k]: v } : p))

  return (
    <div className="space-y-5">
      <Header doc={doc} />
      <div className="flex flex-wrap items-center gap-2">
        {doc.pages.map((p) => (
          <button key={p.id} onClick={() => setSp({ page: String(p.index) })}
            className={cn('min-h-11 rounded-xl border px-4 text-sm', p.index === pageIndex ? 'border-accent text-accent glow' : 'border-line text-muted')}>
            Page {p.index + 1}{p.identification?.template_id ? ` · ${p.identification.template_id} p${p.identification.page_number}` : ''}
          </button>
        ))}
        {lab && <span className="rounded-full border border-accent/50 bg-accent/10 px-3 py-1 text-xs text-accent">Live lab run · {ms(lab.total_ms)} · saved run unchanged</span>}
      </div>

      {/* Stage timeline */}
      <div className="overflow-x-auto pb-2">
        <div className="flex min-w-max items-center gap-1.5">
          {stages.map((s, i) => (
            <div key={s.key} className="flex items-center gap-1.5">
              <button onClick={() => setSelected(s.key)}
                className={cn('flex min-h-11 items-center gap-2 rounded-xl border px-3 text-xs transition',
                  s.key === stage?.key ? 'border-accent bg-accent/10 text-accent glow' : 'border-line text-muted hover:text-fg', !s.applied && 'opacity-50')}>
                <span className="font-mono text-[10px] opacity-70">{String(i + 1).padStart(2, '0')}</span>{s.title}
                <span className="font-mono text-[10px] opacity-70">{ms(s.ms)}</span>
              </button>
              {i < stages.length - 1 && <span className="h-px w-3 bg-line" />}
            </div>
          ))}
        </div>
      </div>

      {stage && (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
          <Card className="min-w-0 p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold">{stage.title}</h2>
                <p className="text-sm text-muted">{stage.why}</p>
              </div>
              <Tip content={<span><b>Why this step exists:</b> {stage.why}</span>}><button aria-label="Why this step exists" className="grid size-11 shrink-0 place-items-center rounded-xl border border-line"><Info className="size-4" /></button></Tip>
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={(lab ? 'lab' : 'saved') + stage.key + stage.image} initial={{ opacity: 0, clipPath: 'inset(0 100% 0 0)' }}
                animate={{ opacity: 1, clipPath: 'inset(0 0% 0 0)' }} exit={{ opacity: 0 }} transition={{ duration: stage.key === 'matching' ? 1.1 : 0.45 }}>
                {stage.image ? (
                  <img src={fileUrl(stage.image)} alt={stage.title} className="mx-auto max-h-[70vh] w-auto max-w-full rounded-xl border border-line bg-black/30" />
                ) : stage.key === 'identification' ? (
                  <IdentCard stage={stage} />
                ) : (
                  <div className="rounded-xl border border-line bg-panel-2 p-4"><Metrics stage={stage} /></div>
                )}
              </motion.div>
            </AnimatePresence>
            {stage.image && prevWithImage?.image && stage.key !== 'matching' && (
              <details className="mt-4 rounded-xl border border-line p-3">
                <summary className="min-h-11 cursor-pointer content-center text-sm"><Layers className="mr-2 inline size-4" />Before / after: {prevWithImage.title} → {stage.title}</summary>
                <div className="mt-3"><CompareView before={fileUrl(prevWithImage.image)} after={fileUrl(stage.image)} label={stage.title} /></div>
              </details>
            )}
            <div className="mt-4"><StageExtras stage={stage} all={stages} doc={doc} pageIndex={pageIndex} /></div>
          </Card>

          <div className="space-y-5">
            <Card>
              <CardTitle icon={<Zap className="size-4" />}>Measured</CardTitle>
              <div className="px-5 pb-5"><Metrics stage={stage} /></div>
            </Card>
            {params && (
              <Card>
                <CardTitle icon={<SlidersHorizontal className="size-4" />} right={
                  <button onClick={() => { setLab(null); setParams(stagesQ.data!.params as Params) }} className="flex min-h-11 items-center gap-1 px-2 text-xs text-muted hover:text-fg"><RotateCcw className="size-3.5" />Saved run</button>
                }>Re-run live</CardTitle>
                <div className="space-y-5 px-5 pb-5">
                  <SliderRow label="Denoise strength (median kernel)" value={params.denoise_strength} min={0} max={9} step={1} onChange={(v) => { set('denoise_strength', v); set('denoise_method', v === 0 ? 'none' : 'median') }} />
                  <SliderRow label="CLAHE clip limit" value={params.clahe_clip} min={0.5} max={8} step={0.5} onChange={(v) => set('clahe_clip', v)} />
                  <SliderRow label="Canny low threshold" value={params.canny_low} min={0} max={200} step={5} onChange={(v) => set('canny_low', v)} />
                  <Select label="Threshold method" value={params.threshold_method} options={['adaptive_gaussian', 'adaptive_mean', 'otsu']} onChange={(v) => set('threshold_method', v)} />
                  <Select label="Feature matcher" value={params.matcher} options={['sift', 'orb']} onChange={(v) => set('matcher', v)} />
                  <p className="text-xs text-muted">{rerun.isPending ? 'Re-running on the server…' : rerun.error ? String(rerun.error) : 'Changes re-run preprocessing and identification on the server (no OCR).'}</p>
                </div>
              </Card>
            )}
            <Card>
              <CardTitle icon={<Timer className="size-4" />}>Stage timings (measured)</CardTitle>
              <div className="px-2 pb-4" style={{ height: Math.max(220, timing.length * 22) }}>
                <ResponsiveContainer>
                  <BarChart data={timing} layout="vertical" margin={{ left: 4, right: 16 }}>
                    <XAxis type="number" tick={{ fill: 'var(--muted)', fontSize: 10 }} unit=" ms" />
                    <YAxis type="category" dataKey="name" width={104} tick={{ fill: 'var(--muted)', fontSize: 10 }} />
                    <RTooltip contentStyle={{ background: '#0d1117', border: '1px solid #222', borderRadius: 12 }} formatter={(v) => ms(Number(v))} />
                    <Bar dataKey="ms" radius={[0, 6, 6, 0]} onClick={(d) => setSelected((d as unknown as { key: string }).key)}>
                      {timing.map((t) => <Cell key={t.key} fill={t.key === stage.key ? '#22d3ee' : '#334155'} cursor="pointer" />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>
          </div>
        </div>
      )}
    </div>
  )
}

function IdentCard({ stage }: { stage: Stage }) {
  const m = stage.metrics as { status: string; template_id: string | null; page_number: number | null; confidence: number; inliers: number }
  return (
    <div className="grid gap-4 rounded-xl border border-line bg-panel-2 p-6 sm:grid-cols-3">
      <div><div className="text-xs text-muted uppercase">Result</div><div className="mt-1 text-2xl font-semibold">{m.status === 'identified' ? `${m.template_id} · page ${m.page_number}` : 'Unknown form'}</div></div>
      <div><div className="text-xs text-muted uppercase">RANSAC inliers</div><div className="mt-1 text-2xl font-semibold tabular-nums">{m.inliers}</div></div>
      <div><div className="text-xs text-muted uppercase">Confidence (documented score)</div><div className="mt-1 text-2xl font-semibold">{pct(m.confidence, 1)}</div></div>
    </div>
  )
}

function SliderRow(p: { label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void }) {
  return (
    <label className="block">
      <div className="mb-1 flex justify-between text-xs text-muted"><span>{p.label}</span><span className="font-mono text-fg">{p.value}</span></div>
      <input type="range" min={p.min} max={p.max} step={p.step} value={p.value} onChange={(e) => p.onChange(+e.target.value)} className="h-11 w-full accent-[var(--accent)]" aria-label={p.label} />
    </label>
  )
}

function Select({ label, value, options, onChange }: { label: string; value: string; options: string[]; onChange: (v: string) => void }) {
  return (
    <label className="block text-xs text-muted">{label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className="mt-1 min-h-11 w-full rounded-xl border border-line bg-panel-2 px-3 text-sm text-fg">
        {options.map((o) => <option key={o} value={o}>{o}</option>)}
      </select>
    </label>
  )
}

function Header({ doc }: { doc?: DocDetail }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="flex items-center gap-2 text-2xl font-semibold"><FlaskConical className="size-6 text-accent" />Vision Lab</h1>
        <p className="text-sm text-muted">{doc ? `${doc.display_name} · ${doc.bank_name ?? 'unidentified'}` : 'Every stage of the real OpenCV pipeline, image by image.'}</p>
      </div>
      {doc && <Link to={`/documents/${doc.id}`}><Button variant="outline">Open review</Button></Link>}
    </div>
  )
}

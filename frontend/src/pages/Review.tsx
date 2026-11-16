// REVIEW: the aligned page with every field box (coloured by confidence) next to the
// field inspector. Selecting a box selects its field and vice versa. Nothing is verified
// until a person presses Verify.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { motion } from 'framer-motion'
import {
  Camera,
  CheckCircle2,
  ChevronUp,
  CreditCard,
  Download,
  FlaskConical,
  Mail,
  MapPin,
  Phone,
  RefreshCw,
  User,
  ZoomIn,
  ZoomOut,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { TransformComponent, TransformWrapper, type ReactZoomPanPinchRef } from 'react-zoom-pan-pinch'
import { toast } from 'sonner'
import { Button, Card, ConfBar, Empty, ErrorState, Skeleton, StatusBadge } from '../components/ui'
import { api, download, fileUrl, type DocDetail, type Field, type StageRun } from '../lib/api'
import { cn, confColour, ms, pct, STATUS_LABEL } from '../lib/utils'

const fieldConf = (f: Field) => f.ocr_confidence ?? f.detection_confidence

function getInitials(name: string | null | undefined): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

function getCustomerSummary(fields: Field[]) {
  const byId = (id: string, group?: string) =>
    fields.find((f) => f.field_id === id && (!group || f.group_id === group))?.normalized_value ||
    fields.find((f) => f.field_id === id && (!group || f.group_id === group))?.raw_text

  const name =
    byId('name_english') || byId('name_boxed') || byId('name_nepali') || 'Unknown Customer'
  const accountNo = byId('bank_account_number')
  const customerId = byId('customer_id')
  const email = byId('email')
  const phone = byId('mobile') || byId('phone')
  const branch = byId('branch_name')

  // Permanent address
  const permParts = [
    byId('address_house_no', 'permanent') ? `House ${byId('address_house_no', 'permanent')}` : null,
    byId('address_tole', 'permanent') ? `Tole ${byId('address_tole', 'permanent')}` : null,
    byId('address_municipality', 'permanent'),
    byId('address_district', 'permanent'),
    byId('address_country', 'permanent'),
  ].filter(Boolean)
  const permAddress = permParts.length > 0 ? permParts.join(', ') : null

  return { name, accountNo, customerId, email, phone, branch, permAddress }
}

function Inspector({ fields, selected, onSelect, docId }: { fields: Field[]; selected: number | null; onSelect: (id: number) => void; docId: number }) {
  const qc = useQueryClient()
  const sections = useMemo(() => {
    const m = new Map<string, Field[]>()
    for (const f of fields) m.set(f.section, [...(m.get(f.section) ?? []), f])
    return [...m.entries()]
  }, [fields])
  const refresh = () => qc.invalidateQueries({ queryKey: ['doc', String(docId)] })
  return (
    <div className="space-y-5">
      {sections.map(([section, fs]) => (
        <div key={section}>
          <h4 className="mb-2 px-1 text-xs tracking-wide text-muted uppercase">{section}</h4>
          <div className="space-y-2">
            {fs.map((f) => <FieldRow key={f.id} f={f} active={f.id === selected} onSelect={() => onSelect(f.id)} onSaved={refresh} />)}
          </div>
        </div>
      ))}
    </div>
  )
}

function FieldRow({ f, active, onSelect, onSaved }: { f: Field; active: boolean; onSelect: () => void; onSaved: () => void }) {
  const ref = useRef<HTMLDivElement>(null)
  const [value, setValue] = useState(f.normalized_value ?? '')
  useEffect(() => setValue(f.normalized_value ?? ''), [f.normalized_value])
  useEffect(() => { if (active) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' }) }, [active])
  const save = useMutation({ mutationFn: () => api(`/fields/${f.id}`, { method: 'PATCH', body: JSON.stringify({ value }) }), onSuccess: () => { toast.success('Saved (still needs Verify)'); onSaved() }, onError: (e) => toast.error(String(e)) })
  const verify = useMutation({ mutationFn: () => api(`/fields/${f.id}/verify`, { method: 'POST' }), onSuccess: () => { toast.success(`${f.display_name} verified`); onSaved() }, onError: (e) => toast.error(String(e)) })
  const conf = fieldConf(f)
  const low = f.status === 'needs_review' || f.status === 'unreadable'
  const dev = /[ऀ-ॿ]/.test(value + (f.raw_text ?? ''))
  const hasValue = !!(f.normalized_value || f.raw_text)

  return (
    <div ref={ref} onClick={onSelect}
      className={cn('cursor-pointer rounded-xl border p-3 transition', active ? 'border-accent bg-accent/8 glow' : low ? 'border-warn/40 bg-warn/5' : 'border-line bg-panel-2/40 hover:bg-panel-2')}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-muted">{f.display_name}</div>
          <div className="truncate text-[10px] text-muted/70">{[f.group_id, f.row_index ? `row ${f.row_index}` : null, f.field_id].filter(Boolean).join(' · ')}</div>
        </div>
        <StatusBadge status={f.status} />
      </div>

      {/* Immediately visible extracted value */}
      <div className="mt-2 flex items-baseline justify-between gap-2 border-t border-line/40 pt-2">
        <div className={cn(
          'truncate text-sm font-semibold',
          hasValue ? 'text-fg' : 'text-xs font-normal italic text-muted',
          dev && 'devanagari'
        )}>
          {f.field_type === 'visual' ? (
            <span className="inline-flex items-center gap-1.5 text-xs font-normal text-accent">
              <Camera className="size-3.5" /> Visual crop captured
            </span>
          ) : f.checkbox ? (
            <span className="text-xs font-medium text-accent">
              ☑ {f.normalized_value || 'Option selected'}
            </span>
          ) : (
            f.normalized_value || f.raw_text || '— (empty field)'
          )}
        </div>
        {f.ocr_confidence !== null && (
          <span className="shrink-0 font-mono text-[11px] text-muted">
            {Math.round(f.ocr_confidence * 100)}%
          </span>
        )}
      </div>

      {active && (
        <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: 'auto' }} className="mt-3 space-y-3" onClick={(e) => e.stopPropagation()}>
          {f.crop_path && <img src={fileUrl(f.crop_path)} alt="field crop" className="max-h-24 w-full rounded-lg bg-white object-contain" />}
          {f.checkbox ? (
            <div className="space-y-1.5">
              {f.checkbox.map((o) => (
                <div key={o.option_id} className="flex items-center justify-between rounded-lg border border-line px-2.5 py-1.5 text-xs">
                  <span className={cn(o.state === 'selected' && 'font-semibold text-good')}>{o.option_id}</span>
                  <span className="font-mono text-muted">ink {o.fill_ratio.toFixed(2)} vs blank {o.baseline_ratio.toFixed(2)} → {o.state}</span>
                </div>
              ))}
            </div>
          ) : f.field_type !== 'visual' ? (
            <div className="grid gap-2 text-xs">
              <div><span className="text-muted">Raw OCR:</span> <span className={cn('font-mono', dev && 'devanagari')}>{f.raw_text ?? '—'}</span></div>
            </div>
          ) : null}
          {f.field_type !== 'visual' && (
            <input value={value} onChange={(e) => setValue(e.target.value)} aria-label={`${f.display_name} value`}
              className={cn('min-h-11 w-full rounded-xl border border-line bg-bg px-3 text-sm outline-none focus:border-accent', dev && 'devanagari')} />
          )}
          <ConfBar value={f.ocr_confidence} label={f.engine === 'checkbox_fill' ? 'Checkbox confidence' : 'OCR confidence'} />
          <ConfBar value={f.detection_confidence} label="Box confidence (alignment × snap IoU)" />
          {f.validation_messages.length > 0 && <ul className="list-disc pl-5 text-xs text-warn">{f.validation_messages.map((m) => <li key={m}>{m}</li>)}</ul>}
          <div className="flex gap-2">
            {f.field_type !== 'visual' && <Button variant="outline" className="flex-1" loading={save.isPending} disabled={value === (f.normalized_value ?? '')} onClick={() => save.mutate()}>Save edit</Button>}
            <Button className="flex-1" loading={verify.isPending} disabled={f.status === 'verified'} onClick={() => verify.mutate()}><CheckCircle2 className="size-4" />{f.status === 'verified' ? 'Verified' : 'Verify'}</Button>
          </div>
        </motion.div>
      )}
      {!active && conf !== null && <div className="mt-2"><div className="h-1 overflow-hidden rounded-full bg-line"><div className="h-full rounded-full" style={{ width: `${(conf ?? 0) * 100}%`, background: confColour(conf) }} /></div></div>}
    </div>
  )
}

export default function Review() {
  const { id } = useParams()
  const [pageIndex, setPageIndex] = useState(0)
  const [selected, setSelected] = useState<number | null>(null)
  const [sheet, setSheet] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const zoom = useRef<ReactZoomPanPinchRef>(null)
  const docQ = useQuery({ queryKey: ['doc', id], queryFn: () => api<DocDetail>(`/documents/${id}`),
    refetchInterval: (q) => (q.state.data && ['uploaded', 'processing'].includes(q.state.data.status) ? 1500 : false) })
  const stagesQ = useQuery({ queryKey: ['stages', id, pageIndex], queryFn: () => api<StageRun>(`/documents/${id}/pages/${pageIndex}/stages`), enabled: !!docQ.data?.pages.find((p) => p.index === pageIndex)?.has_stages, retry: false })
  const doc = docQ.data
  const page = doc?.pages.find((p) => p.index === pageIndex)
  const allFields = doc?.fields.filter((f) => f.page_id === page?.id) ?? []
  const fields = showAll ? allFields : allFields.filter((f) => f.status !== 'empty')
  const ident = stagesQ.data?.identification as { template_size?: [number, number] } | undefined
  const size = ident?.template_size ?? [2481, 3508]
  const aligned = stagesQ.data?.registration?.aligned_image
  const customer = useMemo(() => getCustomerSummary(doc?.fields ?? []), [doc?.fields])

  if (docQ.isLoading) return <div className="grid gap-5 lg:grid-cols-[1fr_420px]"><Skeleton className="h-[75vh]" /><Skeleton className="h-[75vh]" /></div>
  if (docQ.error) return <ErrorState error={docQ.error} />
  if (!doc) return null
  const running = ['uploaded', 'processing'].includes(doc.status)
  const job = doc.jobs[0]
  const counts = doc.field_counts

  const select = (fid: number) => {
    setSelected(fid)
    const el = document.getElementById(`box-${fid}`)
    if (el && zoom.current) zoom.current.zoomToElement(el as unknown as HTMLElement, 2.2, 400)
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold">{doc.display_name}</h1>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-sm text-muted">
            <StatusBadge status={doc.status} />
            <span>{doc.bank_name ?? 'Unidentified form'}</span>
            {doc.template_confidence !== null && <span>· identification {pct(doc.template_confidence, 1)}</span>}
            {doc.processing_seconds !== null && <span>· processed in {doc.processing_seconds.toFixed(1)} s</span>}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Link to={`/lab/${doc.id}?page=${pageIndex}`}><Button variant="outline"><FlaskConical className="size-4" />Vision Lab</Button></Link>
          <Button variant="outline" onClick={() => download(`/documents/${doc.id}/export?format=json`, `document_${doc.id}.json`)}><Download className="size-4" />JSON</Button>
          <Button variant="outline" onClick={() => download(`/documents/${doc.id}/export?format=csv`, `document_${doc.id}.csv`)}><Download className="size-4" />CSV</Button>
          <Button variant="ghost" onClick={() => api(`/documents/${doc.id}/process`, { method: 'POST', body: '{}' }).then(() => { toast('Reprocessing started'); docQ.refetch() })}><RefreshCw className="size-4" />Reprocess</Button>
        </div>
      </div>

      {/* Processing timeline (measured per-stage durations of the latest job) */}
      {job && (
        <Card className="px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs">
            <span className="text-muted">Job #{job.id} · {job.status}</span>
            {Object.entries(job.stage_timings ?? {}).filter(([k]) => k !== 'total').map(([k, v]) => <span key={k} className="rounded-lg border border-line px-2 py-1 font-mono">{k.toLowerCase()} {ms(v * 1000)}</span>)}
            {job.stage_timings?.total !== undefined && <span className="font-mono text-accent">total {ms(job.stage_timings.total * 1000)}</span>}
            {running && <span className="flex items-center gap-2"><span className="h-1.5 w-28 overflow-hidden rounded-full bg-line"><span className="block h-full bg-accent transition-all" style={{ width: `${job.progress * 100}%` }} /></span>{job.message}</span>}
            <span className="ml-auto flex flex-wrap gap-2">{Object.entries(counts).map(([k, v]) => <span key={k}>{STATUS_LABEL[k] ?? k}: <b>{v}</b></span>)}</span>
          </div>
        </Card>
      )}

      {/* Quick Customer Profile Summary Card */}
      {customer.name && customer.name !== 'Unknown Customer' && (
        <Card className="border border-accent/25 bg-gradient-to-r from-accent/10 via-panel to-panel-2 p-4">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div className="flex items-center gap-3.5">
              <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-accent/30 bg-accent/20 text-base font-bold text-accent shadow-inner">
                {getInitials(customer.name)}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-bold uppercase tracking-wider text-accent">Scanned Customer</span>
                  <StatusBadge status={doc.status} />
                </div>
                <h2 className="text-xl font-bold tracking-tight text-fg">{customer.name}</h2>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs">
              {customer.accountNo && (
                <div className="flex items-center gap-1.5 text-muted">
                  <CreditCard className="size-4 text-accent" />
                  <span>A/C: <b className="font-mono text-fg">{customer.accountNo}</b></span>
                </div>
              )}
              {customer.customerId && (
                <div className="flex items-center gap-1.5 text-muted">
                  <User className="size-4 text-accent" />
                  <span>Cust ID: <b className="font-mono text-fg">{customer.customerId}</b></span>
                </div>
              )}
              {customer.permAddress && (
                <div className="flex items-center gap-1.5 text-muted">
                  <MapPin className="size-4 text-accent" />
                  <span>Address: <b className="text-fg">{customer.permAddress}</b></span>
                </div>
              )}
              {customer.email && (
                <div className="flex items-center gap-1.5 text-muted">
                  <Mail className="size-4 text-accent" />
                  <span>Email: <b className="text-fg">{customer.email}</b></span>
                </div>
              )}
              {customer.phone && (
                <div className="flex items-center gap-1.5 text-muted">
                  <Phone className="size-4 text-accent" />
                  <span>Phone: <b className="font-mono text-fg">{customer.phone}</b></span>
                </div>
              )}
            </div>
          </div>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        {doc.pages.map((p) => (
          <button key={p.id} onClick={() => { setPageIndex(p.index); setSelected(null) }} className={cn('min-h-11 rounded-xl border px-4 text-sm', p.index === pageIndex ? 'border-accent text-accent glow' : 'border-line text-muted')}>
            Page {p.index + 1}{p.identification?.page_number ? ` (form p${p.identification.page_number})` : ''}
          </button>
        ))}
        <label className="ml-auto flex min-h-11 items-center gap-2 text-sm text-muted"><input type="checkbox" checked={showAll} onChange={(e) => setShowAll(e.target.checked)} className="size-4 accent-[var(--accent)]" />Show empty fields</label>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_420px]">
        <Card className="relative min-w-0 overflow-hidden p-2">
          {running && !aligned ? (
            <div className="relative grid h-[70vh] place-items-center overflow-hidden rounded-xl bg-panel-2">
              {page && <img src={fileUrl(page.original_path)} alt="uploaded page" className="max-h-full opacity-60" />}
              <motion.div className="scanline absolute inset-x-0 h-24" animate={{ top: ['-10%', '100%'] }} transition={{ duration: 2.2, repeat: Infinity, ease: 'linear' }} />
              <div className="absolute bottom-4 rounded-xl bg-black/70 px-4 py-2 text-sm text-white">{job?.message ?? 'Queued'} · {Math.round((job?.progress ?? 0) * 100)}%</div>
            </div>
          ) : !aligned ? (
            <Empty title={page?.identification?.status === 'unknown' ? 'This page did not match any enrolled form' : 'No aligned page available'}>
              {page?.identification?.status === 'unknown' ? 'Unknown form is a valid outcome: no template had enough consistent features. See the Vision Lab for the matching scores.' : 'Process the document to see the aligned page.'}
            </Empty>
          ) : (
            <TransformWrapper ref={zoom} minScale={0.5} maxScale={8} limitToBounds={false} centerOnInit>
              {({ zoomIn, zoomOut, resetTransform }) => (
                <>
                  <div className="absolute top-3 right-3 z-10 flex gap-1">
                    <button aria-label="Zoom in" onClick={() => zoomIn()} className="grid size-11 place-items-center rounded-xl border border-line bg-bg/80"><ZoomIn className="size-4" /></button>
                    <button aria-label="Zoom out" onClick={() => zoomOut()} className="grid size-11 place-items-center rounded-xl border border-line bg-bg/80"><ZoomOut className="size-4" /></button>
                    <button aria-label="Reset view" onClick={() => resetTransform()} className="grid h-11 place-items-center rounded-xl border border-line bg-bg/80 px-3 text-xs">Fit</button>
                  </div>
                  <TransformComponent wrapperStyle={{ width: '100%', height: '75vh' }} contentStyle={{ width: '100%', height: '75vh', justifyContent: 'center' }}>
                    <svg viewBox={`0 0 ${size[0]} ${size[1]}`} className="h-full w-auto max-w-full">
                      <image href={fileUrl(aligned)} width={size[0]} height={size[1]} />
                      {fields.map((f, i) => {
                        if (!f.bbox) return null
                        const [x, y, w, h] = f.bbox
                        const c = f.status === 'verified' ? '#22d3ee' : confColour(fieldConf(f))
                        const act = f.id === selected
                        return (
                          <motion.rect key={f.id} id={`box-${f.id}`} x={x} y={y} width={w} height={h} rx={6}
                            initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: Math.min(i * 0.02, 1.2) }}
                            fill={act ? `${c}33` : `${c}14`} stroke={c} strokeWidth={act ? 7 : 3.5}
                            style={{ cursor: 'pointer', filter: act ? `drop-shadow(0 0 12px ${c})` : undefined }}
                            onClick={() => { setSelected(f.id); setSheet(true) }}>
                            <title>{`${f.display_name}: ${f.normalized_value ?? ''} (${STATUS_LABEL[f.status]})`}</title>
                          </motion.rect>
                        )
                      })}
                    </svg>
                  </TransformComponent>
                </>
              )}
            </TransformWrapper>
          )}
          <div className="flex flex-wrap gap-3 px-2 pt-2 text-[11px] text-muted">
            <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm bg-good" />confidence ≥ 75%</span>
            <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm bg-warn" />45–75%</span>
            <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm bg-bad" />&lt; 45%</span>
            <span className="flex items-center gap-1"><i className="size-2.5 rounded-sm bg-accent" />verified by a person</span>
          </div>
        </Card>

        {/* Desktop inspector */}
        <Card className="hidden max-h-[calc(75vh+3rem)] overflow-auto p-4 lg:block">
          {fields.length ? <Inspector fields={fields} selected={selected} onSelect={select} docId={doc.id} /> : <Empty title={running ? 'Fields appear when processing finishes' : 'No fields on this page'} />}
        </Card>
      </div>

      {/* Mobile bottom sheet inspector */}
      <div className={cn('fixed inset-x-0 bottom-14 z-40 rounded-t-3xl border-t border-line bg-bg/95 backdrop-blur-xl transition-[max-height] lg:hidden', sheet ? 'max-h-[70vh]' : 'max-h-16')}>
        <button onClick={() => setSheet(!sheet)} className="flex min-h-16 w-full items-center justify-between px-5 text-sm">
          <span>{fields.length} fields · {fields.filter((f) => f.status === 'needs_review' || f.status === 'unreadable').length} to review</span>
          <ChevronUp className={cn('size-5 transition', sheet && 'rotate-180')} />
        </button>
        {sheet && <div className="max-h-[calc(70vh-4rem)] overflow-auto px-4 pb-6"><Inspector fields={fields} selected={selected} onSelect={select} docId={doc.id} /></div>}
      </div>
    </div>
  )
}

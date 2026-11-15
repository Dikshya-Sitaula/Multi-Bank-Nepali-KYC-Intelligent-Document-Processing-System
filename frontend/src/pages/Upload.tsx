// UPLOAD: drag-and-drop or camera capture, reorder pages, then a LIVE stepper that follows
// the real background job (stage names and timings come from the job record).
import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { AlertTriangle, ArrowDown, ArrowUp, Camera, Check, FileUp, FlaskConical, GripVertical, Loader2, X } from 'lucide-react'
import { useEffect, useRef, useState, type DragEvent } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, CardTitle, ErrorState } from '../components/ui'
import { api, type Job } from '../lib/api'
import { cn, ms } from '../lib/utils'

type Item = { file: File; url: string; key: string }
type UploadResp = { document_id: number; job_id: number; pages: { page: number; filename: string; warnings: string[]; codes: string[]; metrics: Record<string, number | null> }[] }

const STEPS: { key: string; label: string }[] = [
  { key: 'QUEUED', label: 'Uploaded' },
  { key: 'PREPROCESSING', label: 'Preprocessing' },
  { key: 'IDENTIFYING', label: 'Identifying form' },
  { key: 'DETECTING', label: 'Aligning + snapping fields' },
  { key: 'OCR', label: 'Reading text (EasyOCR)' },
  { key: 'STRUCTURING', label: 'Structuring' },
  { key: 'COMPLETED', label: 'Completed' },
]

export default function UploadPage() {
  const [items, setItems] = useState<Item[]>([])
  const [drag, setDrag] = useState(false)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<unknown>(null)
  const [resp, setResp] = useState<UploadResp | null>(null)
  const input = useRef<HTMLInputElement>(null)
  const cam = useRef<HTMLInputElement>(null)

  const add = (files: FileList | null) => {
    if (!files) return
    const next = [...files].filter((f) => /image\/|pdf/.test(f.type) || /\.(pdf|jpe?g|png|tiff?|webp)$/i.test(f.name))
      .map((f) => ({ file: f, url: f.type.startsWith('image/') ? URL.createObjectURL(f) : '', key: `${f.name}-${f.size}-${Math.random()}` }))
    setItems((p) => [...p, ...next])
  }
  const move = (from: number, to: number) => setItems((p) => {
    if (to < 0 || to >= p.length) return p
    const c = [...p]; const [x] = c.splice(from, 1); c.splice(to, 0, x); return c
  })
  const onDrop = (e: DragEvent) => { e.preventDefault(); setDrag(false); add(e.dataTransfer.files) }

  async function upload() {
    setBusy(true); setErr(null)
    try {
      const fd = new FormData()
      items.forEach((it) => fd.append('files', it.file))
      const r = await api<UploadResp>(`/documents?name=${encodeURIComponent(items[0].file.name.replace(/\.[^.]+$/, ''))}`, { method: 'POST', body: fd })
      setResp(r)
    } catch (e) { setErr(e) } finally { setBusy(false) }
  }

  const jobQ = useQuery({
    queryKey: ['job', resp?.job_id], enabled: !!resp?.job_id,
    queryFn: () => api<Job>(`/jobs/${resp!.job_id}`),
    refetchInterval: (q) => (q.state.data && ['COMPLETED', 'FAILED', 'CANCELLED'].includes(q.state.data.status) ? false : 700),
  })
  const job = jobQ.data
  useEffect(() => () => items.forEach((i) => i.url && URL.revokeObjectURL(i.url)), [items])

  const reached = (k: string) => {
    if (!job) return false
    if (job.status === 'COMPLETED') return true
    const order = STEPS.map((s) => s.key)
    const cur = order.indexOf(job.status === 'RUNNING' ? 'QUEUED' : job.status)
    return order.indexOf(k) < cur || (k === 'QUEUED')
  }
  const timing = (k: string) => (k === 'QUEUED' ? undefined : job?.stage_timings?.[k])

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">Upload a KYC form</h1>
        <p className="text-sm text-muted">Photos or scans of all pages (JPEG, PNG, TIFF, WEBP or PDF). Pages are processed in the order shown.</p>
      </div>

      {!resp && (
        <>
          <div onDragOver={(e) => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)} onDrop={onDrop}
            className={cn('glass grid min-h-64 place-items-center rounded-3xl border-2 border-dashed p-8 text-center transition', drag ? 'border-accent glow' : 'border-line')}>
            <div className="space-y-4">
              <motion.div animate={{ y: drag ? -6 : 0 }} className="mx-auto grid size-16 place-items-center rounded-2xl bg-accent/12 text-accent"><FileUp className="size-8" /></motion.div>
              <div><p className="text-lg font-medium">Drop form pages here</p><p className="text-sm text-muted">or choose files / take a photo</p></div>
              <div className="flex flex-wrap justify-center gap-2">
                <Button variant="outline" onClick={() => input.current?.click()}><FileUp className="size-4" />Choose files</Button>
                <Button variant="outline" onClick={() => cam.current?.click()}><Camera className="size-4" />Camera</Button>
              </div>
              <input ref={input} type="file" multiple accept="image/*,application/pdf" className="hidden" onChange={(e) => add(e.target.files)} />
              <input ref={cam} type="file" accept="image/*" capture="environment" className="hidden" onChange={(e) => add(e.target.files)} />
            </div>
          </div>

          {items.length > 0 && (
            <Card className="p-4">
              <div className="mb-3 flex items-center justify-between"><span className="text-sm text-muted">{items.length} file(s) · drag or use arrows to reorder</span>
                <Button onClick={upload} loading={busy}>Upload and process</Button></div>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-5">
                <AnimatePresence>
                  {items.map((it, i) => (
                    <motion.div layout key={it.key} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}
                      draggable onDragStart={() => setDragIdx(i)} onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.stopPropagation(); if (dragIdx !== null) move(dragIdx, i); setDragIdx(null) }}
                      className="group relative overflow-hidden rounded-xl border border-line bg-panel-2">
                      {it.url ? <img src={it.url} alt={it.file.name} className="aspect-[3/4] w-full object-cover" /> : <div className="grid aspect-[3/4] place-items-center text-xs text-muted">PDF</div>}
                      <div className="absolute top-1.5 left-1.5 rounded-md bg-black/70 px-1.5 text-xs text-white">{i + 1}</div>
                      <GripVertical className="absolute top-1.5 right-10 size-4 text-white/70" />
                      <button aria-label="Remove" onClick={() => setItems((p) => p.filter((_, j) => j !== i))} className="absolute top-0 right-0 grid size-11 place-items-center text-white/80 hover:text-white"><X className="size-4" /></button>
                      <div className="flex items-center justify-between gap-1 p-1.5">
                        <span className="truncate text-[11px] text-muted">{it.file.name}</span>
                        <span className="flex shrink-0">
                          <button aria-label="Move earlier" onClick={() => move(i, i - 1)} className="grid size-9 place-items-center"><ArrowUp className="size-3.5" /></button>
                          <button aria-label="Move later" onClick={() => move(i, i + 1)} className="grid size-9 place-items-center"><ArrowDown className="size-3.5" /></button>
                        </span>
                      </div>
                    </motion.div>
                  ))}
                </AnimatePresence>
              </div>
              {err !== null && <div className="mt-3"><ErrorState error={err} /></div>}
            </Card>
          )}
        </>
      )}

      {resp && (
        <div className="grid gap-5 md:grid-cols-[1fr_1.2fr]">
          <Card>
            <CardTitle>Page quality (measured on upload)</CardTitle>
            <div className="space-y-3 px-5 pb-5">
              {resp.pages.map((p) => (
                <div key={p.page} className="rounded-xl border border-line p-3">
                  <div className="flex items-center justify-between text-sm"><span className="truncate">Page {p.page} · {p.filename}</span>
                    {p.warnings.length ? <AlertTriangle className="size-4 text-warn" /> : <Check className="size-4 text-good" />}</div>
                  <div className="mt-2 flex flex-wrap gap-1.5 text-[11px] font-mono text-muted">
                    <span className="rounded-md border border-line px-1.5">{p.metrics.width_px}×{p.metrics.height_px}px</span>
                    <span className="rounded-md border border-line px-1.5">blur(var Lap) {p.metrics.sharpness_laplacian_var}</span>
                    <span className="rounded-md border border-line px-1.5">skew {p.metrics.skew_deg ?? '—'}°</span>
                    <span className="rounded-md border border-line px-1.5">glare {p.metrics.glare_fraction ?? 'n/a'}</span>
                  </div>
                  {p.warnings.map((w) => <p key={w} className="mt-2 text-xs text-warn">{w}</p>)}
                </div>
              ))}
            </div>
          </Card>
          <Card>
            <CardTitle right={<span className="font-mono text-xs text-muted">job #{resp.job_id}</span>}>Live processing</CardTitle>
            <ol className="space-y-1 px-5 pb-5">
              {STEPS.map((s) => {
                const done = reached(s.key) && job?.status !== s.key
                const active = job?.status === s.key || (s.key === 'QUEUED' && (job?.status === 'RUNNING' || job?.status === 'QUEUED'))
                return (
                  <li key={s.key} className={cn('flex min-h-11 items-center gap-3 rounded-xl px-3', active && 'bg-accent/10')}>
                    <span className={cn('grid size-7 place-items-center rounded-full border text-xs', done ? 'border-good bg-good/15 text-good' : active ? 'border-accent text-accent glow' : 'border-line text-muted')}>
                      {done ? <Check className="size-4" /> : active ? <Loader2 className="size-4 animate-spin" /> : null}
                    </span>
                    <span className={cn('flex-1 text-sm', !done && !active && 'text-muted')}>{s.label}</span>
                    <span className="font-mono text-xs text-muted">{timing(s.key) !== undefined ? ms(timing(s.key)! * 1000) : ''}</span>
                  </li>
                )
              })}
            </ol>
            {job && (
              <div className="space-y-3 px-5 pb-5">
                <div className="h-2 overflow-hidden rounded-full bg-panel-2"><motion.div className="h-full rounded-full bg-accent" animate={{ width: `${job.progress * 100}%` }} /></div>
                <p className="text-xs text-muted">{job.message}</p>
                {job.status === 'FAILED' && <ErrorState error={new Error(job.error ?? 'failed')} />}
                {job.status === 'COMPLETED' && (
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/documents/${resp.document_id}`}><Button>Review fields</Button></Link>
                    <Link to={`/lab/${resp.document_id}`}><Button variant="outline"><FlaskConical className="size-4" />Vision Lab</Button></Link>
                    <Button variant="ghost" onClick={() => { setResp(null); setItems([]) }}>Upload another</Button>
                  </div>
                )}
              </div>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}

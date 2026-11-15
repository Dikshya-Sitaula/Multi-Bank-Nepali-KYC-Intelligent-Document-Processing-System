import { useQuery } from '@tanstack/react-query'
import { Search as SearchIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorState, Skeleton, StatusBadge } from '../components/ui'
import { api, fileUrl, type Field, type Paged } from '../lib/api'
import { cn } from '../lib/utils'

type Hit = Field & { document: { id: number; display_name: string; status: string } }

function Highlight({ text, q }: { text: string; q: string }) {
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i < 0 || !q) return <>{text}</>
  return <>{text.slice(0, i)}<mark className="rounded bg-accent/30 px-0.5 text-fg">{text.slice(i, i + q.length)}</mark>{text.slice(i + q.length)}</>
}

export default function SearchPage() {
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [field, setField] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  useEffect(() => { const t = setTimeout(() => { setQ(input.trim()); setPage(1) }, 300); return () => clearTimeout(t) }, [input])
  const params = new URLSearchParams({ q, page: String(page), page_size: '20' })
  if (field) params.set('field_id', field)
  if (status) params.set('status', status)
  const { data, isLoading, error, isFetching } = useQuery({ queryKey: ['search', params.toString()], queryFn: () => api<Paged<Hit>>(`/search?${params}`), enabled: q.length > 0 })
  const fieldsQ = useQuery({ queryKey: ['vocab'], queryFn: () => api<{ fields: { id: string; display_name: string }[] }>('/fields') })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Search extracted fields</h1>
      <Card className="flex flex-wrap gap-3 p-3">
        <div className="relative min-w-0 flex-1">
          <SearchIcon className="absolute top-3.5 left-3 size-4 text-muted" />
          <input autoFocus value={input} onChange={(e) => setInput(e.target.value)} placeholder="Name, citizenship no., mobile, district… (English or नेपाली)"
            className="min-h-11 w-full rounded-xl border border-line bg-panel-2 pr-3 pl-9 text-sm" />
        </div>
        <select value={field} onChange={(e) => setField(e.target.value)} className="min-h-11 max-w-full rounded-xl border border-line bg-panel-2 px-3 text-sm" aria-label="Field">
          <option value="">Any field</option>{fieldsQ.data?.fields.map((f) => <option key={f.id} value={f.id}>{f.display_name}</option>)}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="min-h-11 rounded-xl border border-line bg-panel-2 px-3 text-sm" aria-label="Status">
          <option value="">Any status</option>{['auto_accepted', 'needs_review', 'verified', 'unreadable'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
      </Card>
      {!q ? <Card><Empty title="Type to search" icon={<SearchIcon className="size-7" />}>Search runs on the server over raw OCR text and normalised values.</Empty></Card>
        : isLoading ? <Skeleton className="h-80" /> : error ? <ErrorState error={error} /> : !data?.items.length ? <Card><Empty title={`No results for “${q}”`} /></Card> : (
          <Card className={cn('overflow-hidden transition-opacity', isFetching && 'opacity-70')}>
            {data.items.map((h) => (
              <Link key={h.id} to={`/documents/${h.document.id}`} className="flex min-h-16 flex-wrap items-center gap-4 border-b border-line px-5 py-3 hover:bg-panel-2">
                {h.crop_path && <img src={fileUrl(h.crop_path)} alt="" className="h-10 w-32 rounded-md bg-white object-contain" loading="lazy" />}
                <div className="min-w-0 flex-1">
                  <div className={cn('truncate', /[ऀ-ॿ]/.test(h.normalized_value ?? '') && 'devanagari')}><Highlight text={h.normalized_value ?? h.raw_text ?? ''} q={q} /></div>
                  <div className="truncate text-xs text-muted">{h.display_name}{h.group_id ? ` · ${h.group_id}` : ''} · {h.document.display_name}</div>
                </div>
                <StatusBadge status={h.status} />
              </Link>
            ))}
            <div className="flex items-center justify-between px-5 py-3 text-sm text-muted">
              <span>{data.total} result(s)</span>
              <div className="flex gap-2"><Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
            </div>
          </Card>
        )}
    </div>
  )
}

import { useQuery } from '@tanstack/react-query'
import { FileStack } from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorState, Skeleton, StatusBadge } from '../components/ui'
import { api, type DocSummary, type Paged } from '../lib/api'
import { pct } from '../lib/utils'

export default function Documents() {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState('-created_at')
  const params = new URLSearchParams({ page: String(page), page_size: '15', sort })
  if (status) params.set('status', status)
  if (q) params.set('q', q)
  const { data, isLoading, error } = useQuery({ queryKey: ['docs', params.toString()], queryFn: () => api<Paged<DocSummary>>(`/documents?${params}`), refetchInterval: 4000 })
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">Documents</h1>
      <Card className="flex flex-wrap gap-3 p-3">
        <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1) }} placeholder="Filter by name…" className="min-h-11 min-w-0 flex-1 rounded-xl border border-line bg-panel-2 px-3 text-sm" />
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1) }} className="min-h-11 rounded-xl border border-line bg-panel-2 px-3 text-sm" aria-label="Status">
          <option value="">All statuses</option>{['uploaded', 'processing', 'needs_review', 'verified', 'failed'].map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)} className="min-h-11 rounded-xl border border-line bg-panel-2 px-3 text-sm" aria-label="Sort">
          <option value="-created_at">Newest first</option><option value="created_at">Oldest first</option><option value="display_name">Name</option><option value="-processing_seconds">Slowest</option>
        </select>
      </Card>
      {isLoading ? <Skeleton className="h-96" /> : error ? <ErrorState error={error} /> : !data?.items.length ? (
        <Card><Empty title="No documents match" icon={<FileStack className="size-7" />}><Link to="/upload" className="text-accent">Upload a form</Link></Empty></Card>
      ) : (
        <Card className="overflow-hidden">
          <div className="hidden grid-cols-[1fr_160px_110px_90px_130px] gap-3 border-b border-line px-5 py-3 text-xs text-muted uppercase md:grid">
            <span>Document</span><span>Bank form</span><span>Identified</span><span>Pages</span><span>Status</span>
          </div>
          {data.items.map((d) => (
            <Link key={d.id} to={`/documents/${d.id}`} className="grid min-h-14 grid-cols-[1fr_auto] items-center gap-3 border-b border-line px-5 py-3 hover:bg-panel-2 md:grid-cols-[1fr_160px_110px_90px_130px]">
              <div className="min-w-0"><div className="truncate font-medium">{d.display_name}</div><div className="text-xs text-muted">{new Date(d.created_at).toLocaleString()}</div></div>
              <span className="hidden truncate text-sm md:block">{d.bank_name ?? '—'}</span>
              <span className="hidden font-mono text-sm md:block">{pct(d.template_confidence, 1)}</span>
              <span className="hidden text-sm md:block">{d.page_count}</span>
              <StatusBadge status={d.status} />
            </Link>
          ))}
          <div className="flex items-center justify-between px-5 py-3 text-sm text-muted">
            <span>{data.total} document(s)</span>
            <div className="flex gap-2"><Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</Button></div>
          </div>
        </Card>
      )}
    </div>
  )
}

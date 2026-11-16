import { useQuery } from '@tanstack/react-query'
import {
  ArrowRight,
  Building2,
  Calendar,
  CreditCard,
  Download,
  FileText,
  Mail,
  MapPin,
  Phone,
  Search as SearchIcon,
  User,
  Users,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button, Card, Empty, ErrorState, Skeleton, StatusBadge } from '../components/ui'
import { api, download, fileUrl, type CustomerProfile, type Field, type Paged } from '../lib/api'
import { cn } from '../lib/utils'

type Hit = Field & { document: { id: number; display_name: string; status: string } }

function Highlight({ text, q }: { text: string; q: string }) {
  const i = text.toLowerCase().indexOf(q.toLowerCase())
  if (i < 0 || !q) return <>{text}</>
  return (
    <>
      {text.slice(0, i)}
      <mark className="rounded bg-accent/30 px-0.5 text-fg">{text.slice(i, i + q.length)}</mark>
      {text.slice(i + q.length)}
    </>
  )
}

function getInitials(name: string | null | undefined): string {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function SearchPage() {
  const [tab, setTab] = useState<'customers' | 'fields'>('customers')
  const [input, setInput] = useState('')
  const [q, setQ] = useState('')
  const [field, setField] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    const t = setTimeout(() => {
      setQ(input.trim())
      setPage(1)
    }, 250)
    return () => clearTimeout(t)
  }, [input])

  // Customer Profiles query (synced with customer_profiles table)
  const custParams = new URLSearchParams({ page: String(page), page_size: '20' })
  if (q) custParams.set('q', q)
  if (status) custParams.set('status', status)

  const customersQ = useQuery({
    queryKey: ['customers', custParams.toString()],
    queryFn: () => api<Paged<CustomerProfile>>(`/customers?${custParams}`),
  })

  // Deep field search query
  const fieldParams = new URLSearchParams({ q, page: String(page), page_size: '20' })
  if (field) fieldParams.set('field_id', field)
  if (status) fieldParams.set('status', status)

  const fieldsSearchQ = useQuery({
    queryKey: ['search', fieldParams.toString()],
    queryFn: () => api<Paged<Hit>>(`/search?${fieldParams}`),
    enabled: tab === 'fields' || q.length > 0,
  })

  const vocabQ = useQuery({
    queryKey: ['vocab'],
    queryFn: () => api<{ fields: { id: string; display_name: string }[] }>('/fields'),
  })

  const customerTotal = customersQ.data?.total ?? 0
  const fieldTotal = fieldsSearchQ.data?.total ?? 0
  const totalPages =
    tab === 'customers'
      ? Math.max(1, Math.ceil((customersQ.data?.total ?? 1) / (customersQ.data?.page_size ?? 20)))
      : Math.max(1, Math.ceil((fieldsSearchQ.data?.total ?? 1) / (fieldsSearchQ.data?.page_size ?? 20)))

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Search & Customer Registry</h1>
          <p className="mt-1 text-sm text-muted">
            Explore scanned customer profiles synced directly from verified KYC documents.
          </p>
        </div>
      </div>

      {/* Search & Filter Bar */}
      <Card className="flex flex-wrap items-center gap-3 p-3">
        <div className="relative min-w-[240px] flex-1">
          <SearchIcon className="absolute top-3.5 left-3 size-4 text-muted" />
          <input
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Search by customer name, account no, customer ID, email, address…"
            className="min-h-11 w-full rounded-xl border border-line bg-panel-2 pr-9 pl-9 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none"
          />
          {input && (
            <button
              onClick={() => setInput('')}
              className="absolute top-3.5 right-3 text-muted hover:text-fg"
              title="Clear search"
            >
              <X className="size-4" />
            </button>
          )}
        </div>

        {tab === 'fields' && (
          <select
            value={field}
            onChange={(e) => setField(e.target.value)}
            className="min-h-11 rounded-xl border border-line bg-panel-2 px-3 text-sm"
            aria-label="Field"
          >
            <option value="">Any field</option>
            {vocabQ.data?.fields.map((f) => (
              <option key={f.id} value={f.id}>
                {f.display_name}
              </option>
            ))}
          </select>
        )}

        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="min-h-11 rounded-xl border border-line bg-panel-2 px-3 text-sm"
          aria-label="Status"
        >
          <option value="">All statuses</option>
          {['needs_review', 'verified', 'auto_accepted', 'failed'].map((s) => (
            <option key={s} value={s}>
              {s.replace('_', ' ')}
            </option>
          ))}
        </select>
      </Card>

      {/* Tabs */}
      <div className="flex border-b border-line gap-2">
        <button
          onClick={() => {
            setTab('customers')
            setPage(1)
          }}
          className={cn(
            'flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
            tab === 'customers'
              ? 'border-accent text-accent'
              : 'border-transparent text-muted hover:text-fg'
          )}
        >
          <Users className="size-4" />
          <span>Customer Profiles</span>
          <span className="rounded-full bg-panel-2 px-2 py-0.5 text-xs text-muted">
            {customerTotal}
          </span>
        </button>

        <button
          onClick={() => {
            setTab('fields')
            setPage(1)
          }}
          className={cn(
            'flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm font-medium transition-colors',
            tab === 'fields'
              ? 'border-accent text-accent'
              : 'border-transparent text-muted hover:text-fg'
          )}
        >
          <FileText className="size-4" />
          <span>Raw OCR Field Hits</span>
          {q && (
            <span className="rounded-full bg-panel-2 px-2 py-0.5 text-xs text-muted">
              {fieldTotal}
            </span>
          )}
        </button>
      </div>

      {/* Tab 1: Customer Profiles (Pretty, User-Friendly Cards) */}
      {tab === 'customers' && (
        <div className="space-y-4">
          {customersQ.isLoading ? (
            <div className="grid gap-4 sm:grid-cols-1">
              <Skeleton className="h-44" />
              <Skeleton className="h-44" />
            </div>
          ) : customersQ.error ? (
            <ErrorState error={customersQ.error} />
          ) : !customersQ.data?.items.length ? (
            <Card>
              <Empty
                title={q ? `No customers matching "${q}"` : 'No scanned customers yet'}
                icon={<Users className="size-8" />}
              >
                {q
                  ? 'Try searching with a different name, account number, or customer ID.'
                  : 'Scan and upload a bank KYC form to automatically register customer profiles.'}
              </Empty>
            </Card>
          ) : (
            <div className="grid gap-4">
              {customersQ.data.items.map((c) => (
                <Card
                  key={c.id}
                  className="group relative overflow-hidden p-5 transition-all hover:border-accent/40 hover:shadow-lg"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    {/* Left: Avatar + Identity */}
                    <div className="flex items-start gap-4">
                      {/* Avatar with Initials */}
                      <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl border border-accent/30 bg-accent/15 text-lg font-bold text-accent shadow-inner">
                        {getInitials(c.name_english)}
                      </div>

                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2.5">
                          <h3 className="text-lg font-semibold text-fg">
                            <Highlight text={c.name_english ?? 'Unnamed Customer'} q={q} />
                          </h3>
                          <StatusBadge status={c.verification_status} />
                          {c.nationality && (
                            <span className="rounded-md border border-line bg-panel-2 px-2 py-0.5 text-xs text-muted">
                              {c.nationality}
                            </span>
                          )}
                        </div>

                        <p className="text-xs text-muted">
                          Source Document:{' '}
                          <span className="font-medium text-fg/80">
                            {c.document_display_name ?? `Document #${c.document_id}`}
                          </span>{' '}
                          · Recorded{' '}
                          {c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}
                        </p>
                      </div>
                    </div>

                    {/* Right: Quick Action Buttons */}
                    <div className="flex shrink-0 items-center gap-2">
                      <Button
                        variant="outline"
                        className="h-9 px-3 text-xs"
                        onClick={() =>
                          download(
                            `/documents/${c.document_id}/export?format=csv`,
                            `${(c.name_english || 'customer').replace(/\s+/g, '_')}_kyc.csv`
                          )
                        }
                        title="Download CSV for this customer"
                      >
                        <Download className="mr-1 size-3.5" />
                        CSV
                      </Button>

                      <Link to={`/documents/${c.document_id}`}>
                        <Button className="h-9 px-4 text-xs font-semibold">
                          Review KYC Form
                          <ArrowRight className="ml-1.5 size-3.5" />
                        </Button>
                      </Link>
                    </div>
                  </div>

                  {/* Customer Details Information Grid */}
                  <div className="mt-4 grid grid-cols-1 gap-2.5 rounded-xl border border-line/60 bg-panel-2/60 p-3.5 text-xs sm:grid-cols-2 lg:grid-cols-4">
                    {/* Account No */}
                    <div className="flex items-center gap-2 text-muted">
                      <CreditCard className="size-4 shrink-0 text-accent/80" />
                      <div className="min-w-0">
                        <span className="block text-[10px] uppercase text-muted">Account No</span>
                        <span className="font-mono font-medium text-fg">
                          {c.account_number ? (
                            <Highlight text={c.account_number} q={q} />
                          ) : (
                            <span className="italic text-muted">Not specified</span>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Customer ID */}
                    <div className="flex items-center gap-2 text-muted">
                      <User className="size-4 shrink-0 text-accent/80" />
                      <div className="min-w-0">
                        <span className="block text-[10px] uppercase text-muted">Customer ID</span>
                        <span className="font-mono font-medium text-fg">
                          {c.customer_id ? (
                            <Highlight text={c.customer_id} q={q} />
                          ) : (
                            <span className="italic text-muted">Not specified</span>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* Branch */}
                    <div className="flex items-center gap-2 text-muted">
                      <Building2 className="size-4 shrink-0 text-accent/80" />
                      <div className="min-w-0">
                        <span className="block text-[10px] uppercase text-muted">Branch</span>
                        <span className="truncate font-medium text-fg">
                          {c.branch_name ? (
                            <Highlight text={c.branch_name} q={q} />
                          ) : (
                            <span className="italic text-muted">Head Office / General</span>
                          )}
                        </span>
                      </div>
                    </div>

                    {/* DOB / Demographics */}
                    <div className="flex items-center gap-2 text-muted">
                      <Calendar className="size-4 shrink-0 text-accent/80" />
                      <div className="min-w-0">
                        <span className="block text-[10px] uppercase text-muted">DOB / Gender</span>
                        <span className="font-medium text-fg">
                          {c.dob_bs ?? '—'} · {c.gender ?? '—'} · {c.marital_status ?? '—'}
                        </span>
                      </div>
                    </div>

                    {/* Email */}
                    {c.email && (
                      <div className="flex items-center gap-2 text-muted sm:col-span-2">
                        <Mail className="size-4 shrink-0 text-accent/80" />
                        <div className="min-w-0">
                          <span className="block text-[10px] uppercase text-muted">Email</span>
                          <span className="truncate font-medium text-fg">
                            <Highlight text={c.email} q={q} />
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Mobile */}
                    {c.mobile && (
                      <div className="flex items-center gap-2 text-muted sm:col-span-2">
                        <Phone className="size-4 shrink-0 text-accent/80" />
                        <div className="min-w-0">
                          <span className="block text-[10px] uppercase text-muted">Contact</span>
                          <span className="font-mono font-medium text-fg">
                            <Highlight text={c.mobile} q={q} />
                          </span>
                        </div>
                      </div>
                    )}

                    {/* Permanent Address */}
                    <div className="flex items-start gap-2 text-muted sm:col-span-2 lg:col-span-4">
                      <MapPin className="mt-0.5 size-4 shrink-0 text-accent/80" />
                      <div className="min-w-0 flex-1">
                        <span className="block text-[10px] uppercase text-muted">Permanent Address</span>
                        <span className="font-medium text-fg">
                          {c.permanent_address ? (
                            <Highlight text={c.permanent_address} q={q} />
                          ) : (
                            <span className="italic text-muted">Address not extracted</span>
                          )}
                        </span>
                      </div>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab 2: Raw OCR Field Hits */}
      {tab === 'fields' && (
        <div>
          {!q ? (
            <Card>
              <Empty title="Type to search raw fields" icon={<SearchIcon className="size-8" />}>
                Type a term into the search bar above to look through individual OCR box hits across
                all pages.
              </Empty>
            </Card>
          ) : fieldsSearchQ.isLoading ? (
            <Skeleton className="h-80" />
          ) : fieldsSearchQ.error ? (
            <ErrorState error={fieldsSearchQ.error} />
          ) : !fieldsSearchQ.data?.items.length ? (
            <Card>
              <Empty title={`No raw field matches for “${q}”`} />
            </Card>
          ) : (
            <Card className="overflow-hidden">
              {fieldsSearchQ.data.items.map((h) => (
                <Link
                  key={h.id}
                  to={`/documents/${h.document.id}`}
                  className="flex min-h-16 flex-wrap items-center gap-4 border-b border-line px-5 py-3 transition hover:bg-panel-2"
                >
                  {h.crop_path && (
                    <img
                      src={fileUrl(h.crop_path)}
                      alt=""
                      className="h-10 w-32 rounded-md bg-white object-contain"
                      loading="lazy"
                    />
                  )}
                  <div className="min-w-0 flex-1">
                    <div
                      className={cn(
                        'truncate text-sm font-medium text-fg',
                        /[ऀ-ॿ]/.test(h.normalized_value ?? '') && 'devanagari'
                      )}
                    >
                      <Highlight text={h.normalized_value ?? h.raw_text ?? ''} q={q} />
                    </div>
                    <div className="truncate text-xs text-muted">
                      {h.display_name}
                      {h.group_id ? ` · ${h.group_id}` : ''} · {h.document.display_name}
                    </div>
                  </div>
                  <StatusBadge status={h.status} />
                </Link>
              ))}
            </Card>
          )}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between px-2 text-sm text-muted">
          <span>
            Page {page} of {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}

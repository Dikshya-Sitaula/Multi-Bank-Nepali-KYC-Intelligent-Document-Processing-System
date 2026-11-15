import { useQuery } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'framer-motion'
import { Activity, Database, FileStack, FlaskConical, LayoutDashboard, LogOut, Moon, ScanText, Search, Sun, Upload } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom'
import { api, setToken, type Health, type Job, type Paged } from '../lib/api'
import { cn } from '../lib/utils'
import { Tip } from '../components/ui'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/upload', label: 'Upload', icon: Upload },
  { to: '/documents', label: 'Documents', icon: FileStack },
  { to: '/lab', label: 'Vision Lab', icon: FlaskConical },
  { to: '/search', label: 'Search', icon: Search },
]

function useTheme() {
  const [dark, setDark] = useState(() => {
    try { return localStorage.getItem('theme') !== 'light' } catch { return true }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    try { localStorage.setItem('theme', dark ? 'dark' : 'light') } catch { /* ignore */ }
  }, [dark])
  return [dark, setDark] as const
}

function JobTray() {
  const { data } = useQuery({
    queryKey: ['jobs', 'active'],
    queryFn: () => api<Paged<Job>>('/jobs?active_only=true&page_size=5'),
    refetchInterval: 1500,
  })
  const jobs = data?.items ?? []
  return (
    <AnimatePresence>
      {jobs.length > 0 && (
        <motion.div initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
          className="hidden items-center gap-2 rounded-xl border border-line bg-panel-2 px-3 py-1.5 text-xs md:flex">
          <Activity className="size-3.5 animate-pulse text-accent" />
          {jobs.slice(0, 1).map((j) => (
            <Link key={j.id} to={j.document_id ? `/documents/${j.document_id}` : '#'} className="flex min-w-0 items-center gap-2">
              <span className="max-w-48 truncate">{j.message ?? j.status}</span>
              <span className="h-1.5 w-20 overflow-hidden rounded-full bg-line">
                <span className="block h-full rounded-full bg-accent transition-all" style={{ width: `${Math.round(j.progress * 100)}%` }} />
              </span>
              <span className="font-mono">{Math.round(j.progress * 100)}%</span>
            </Link>
          ))}
          {jobs.length > 1 && <span className="text-muted">+{jobs.length - 1}</span>}
        </motion.div>
      )}
    </AnimatePresence>
  )
}

function StatusChip() {
  const { data, isError } = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health'), refetchInterval: 10000 })
  const ocr = data?.components.find((c) => c.name === 'ocr_models')
  const ok = data && data.database.ok && data.worker.ok
  return (
    <Tip content={
      <div className="space-y-1">
        <div><b>Mode:</b> Template alignment + OpenCV box snapping</div>
        <div><b>YOLO:</b> not trained yet (never used)</div>
        <div><b>OCR:</b> {ocr?.detail ?? '…'}</div>
        <div><b>Database:</b> {data?.database.detail ?? '…'} · <b>Worker:</b> {data?.worker.detail ?? '…'}</div>
      </div>
    }>
      <button className="flex min-h-11 items-center gap-2 rounded-xl border border-line px-3 text-xs">
        <span className={cn('size-2 rounded-full', isError ? 'bg-bad' : ok ? 'bg-good' : 'bg-warn')} />
        <span className="hidden sm:inline">Template-alignment mode</span>
        <span className="sm:hidden">Status</span>
        <Database className="size-3.5 text-muted" />
        <span className={cn('hidden lg:inline', ocr?.ok ? 'text-good' : 'text-warn')}>OCR {ocr?.ok ? 'ready' : 'loading'}</span>
      </button>
    </Tip>
  )
}

export default function AppShell() {
  const [dark, setDark] = useTheme()
  const nav = useNavigate()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: () => api<Health>('/health') })
  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-line px-3 py-5 lg:flex">
        <Link to="/" className="mb-8 flex items-center gap-2.5 px-2">
          <div className="grid size-9 place-items-center rounded-xl bg-accent text-accent-fg glow"><ScanText className="size-5" /></div>
          <div><div className="text-sm font-semibold">KYC Vision</div><div className="text-xs text-muted">Nepali KYC · CV pipeline</div></div>
        </Link>
        <nav className="space-y-1">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) => cn('flex min-h-11 items-center gap-3 rounded-xl px-3 text-sm transition',
              isActive ? 'bg-accent/12 text-accent glow' : 'text-muted hover:bg-panel-2 hover:text-fg')}>
              <Icon className="size-4" />{label}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto space-y-1">
          <button onClick={() => setDark(!dark)} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-sm text-muted hover:bg-panel-2 hover:text-fg">
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}{dark ? 'Light theme' : 'Dark theme'}
          </button>
          <button onClick={() => { setToken(null); nav('/login') }} className="flex min-h-11 w-full items-center gap-3 rounded-xl px-3 text-sm text-muted hover:bg-panel-2 hover:text-fg">
            <LogOut className="size-4" />Sign out
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col pb-20 lg:pb-0">
        <header className="sticky top-0 z-30 flex items-center gap-3 border-b border-line bg-bg/80 px-4 py-2.5 backdrop-blur-xl md:px-6">
          <Link to="/" className="grid size-9 place-items-center rounded-xl bg-accent text-accent-fg lg:hidden"><ScanText className="size-5" /></Link>
          <div className="min-w-0 flex-1"><JobTray /></div>
          <StatusChip />
          <button onClick={() => setDark(!dark)} aria-label="Toggle theme" className="grid size-11 place-items-center rounded-xl border border-line lg:hidden">
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </button>
        </header>
        {health && (
          <div className="border-b border-line bg-warn/8 px-4 py-2 text-xs text-warn md:px-6">
            <b>What is real here:</b> {health.banners.join(' ')} Every image, box and number comes from the backend and the database. Demo forms are SYNTHETIC (fictional people).
          </div>
        )}
        <main className="mx-auto w-full max-w-[1600px] min-w-0 flex-1 px-4 py-6 md:px-6"><Outlet /></main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-5 border-t border-line bg-bg/90 backdrop-blur-xl lg:hidden">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => cn('flex min-h-14 flex-col items-center justify-center gap-1 text-[11px]', isActive ? 'text-accent' : 'text-muted')}>
            <Icon className="size-5" /><span className="truncate">{label}</span>
          </NavLink>
        ))}
      </nav>
    </div>
  )
}

import { motion } from 'framer-motion'
import { ScanText } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, ErrorState } from '../components/ui'
import { api, setToken } from '../lib/api'

export default function Login() {
  const nav = useNavigate()
  const [username, setU] = useState('')
  const [password, setP] = useState('')
  const [err, setErr] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault()
    setBusy(true); setErr(null)
    try {
      const r = await api<{ access_token: string }>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })
      setToken(r.access_token)
      nav('/')
    } catch (ex) { setErr(ex) } finally { setBusy(false) }
  }
  return (
    <div className="grid min-h-full place-items-center p-4">
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="w-full max-w-sm">
        <Card className="p-7">
          <div className="mb-6 flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-xl bg-accent text-accent-fg glow"><ScanText className="size-6" /></div>
            <div><h1 className="text-lg font-semibold">KYC Vision</h1><p className="text-xs text-muted">Multi-bank Nepali KYC document processing</p></div>
          </div>
          <form onSubmit={submit} className="space-y-4">
            <input className="min-h-11 w-full rounded-xl border border-line bg-panel-2 px-3 text-sm outline-none focus:border-accent" placeholder="Username"
              autoComplete="username" value={username} onChange={(e) => setU(e.target.value)} required />
            <input className="min-h-11 w-full rounded-xl border border-line bg-panel-2 px-3 text-sm outline-none focus:border-accent" placeholder="Password" type="password"
              autoComplete="current-password" value={password} onChange={(e) => setP(e.target.value)} required />
            {err !== null && <ErrorState error={err} />}
            <Button className="w-full" loading={busy}>Sign in</Button>
          </form>
          <p className="mt-5 text-xs text-muted">Accounts are created with <code>create_user.py</code>; there is no default password.</p>
        </Card>
      </motion.div>
    </div>
  )
}

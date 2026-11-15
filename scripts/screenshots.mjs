// Responsive screenshots with an installed Chrome/Edge via the DevTools protocol (no
// extra downloads). Logs in through the real API, then captures pages at given widths and
// reports horizontal overflow (document wider than the viewport).
//
//   node scripts/screenshots.mjs <username> <password-env-var> <outdir> <path>@<w1,w2> ...
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const [user, pwEnv, outDir, ...targets] = process.argv.slice(2)
const BASE = 'http://localhost:5173'
const BROWSER = process.env.BROWSER_EXE || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const PORT = Number(process.env.CDP_PORT || 9333)
mkdirSync(outDir, { recursive: true })

const res = await fetch(`${BASE}/api/v1/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: user, password: process.env[pwEnv] }),
})
if (!res.ok) throw new Error(`login failed: ${res.status}`)
const { access_token: token } = await res.json()

let proc = null
try { await fetch(`http://127.0.0.1:${PORT}/json/version`) } catch {
  proc = spawn(BROWSER, ['--headless=new', `--remote-debugging-port=${PORT}`, '--user-data-dir=' + resolve(outDir, '.profile'),
    '--hide-scrollbars', '--force-device-scale-factor=1', 'about:blank'], { stdio: 'ignore' })
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let wsUrl
for (let i = 0; i < 150 && !wsUrl; i++) {
  try {
    const t = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()
    wsUrl = t.find((x) => x.type === 'page')?.webSocketDebuggerUrl
    if (!wsUrl) { const n = await (await fetch(`http://127.0.0.1:${PORT}/json/new?about:blank`, { method: 'PUT' })).json(); wsUrl = n.webSocketDebuggerUrl }
  } catch { await sleep(300) }
}
if (!wsUrl) throw new Error('browser did not start')
const ws = new WebSocket(wsUrl)
await new Promise((r) => ws.addEventListener('open', r))
let id = 0
const pending = new Map()
ws.addEventListener('message', (e) => { const m = JSON.parse(e.data); if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id) } })
const send = (method, params = {}) => new Promise((r) => { const i = ++id; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })) })

await send('Page.enable')
await send('Page.navigate', { url: `${BASE}/login` })
await sleep(1500)
await send('Runtime.evaluate', { expression: `localStorage.setItem('kyc_token', ${JSON.stringify(token)}); localStorage.setItem('theme','dark')` })

const report = []
for (const t of targets) {
  const at = t.lastIndexOf('@'); const path = t.slice(0, at); const widths = t.slice(at + 1)
  for (const w of widths.split(',').map(Number)) {
    const mobile = w < 768
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: mobile ? 844 : 900, deviceScaleFactor: 1, mobile })
    await send('Page.navigate', { url: BASE + path })
    await sleep(6000)
    const ov = await send('Runtime.evaluate', { expression: 'JSON.stringify({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth, h: document.documentElement.scrollHeight, broken: [...document.images].filter(i => i.complete && i.naturalWidth === 0).length})', returnByValue: true })
    const m = JSON.parse(ov.result.result.value)
    await send('Emulation.setDeviceMetricsOverride', { width: w, height: Math.max(600, Math.min(m.h, 3000)), deviceScaleFactor: 1, mobile })
    await sleep(800)
    const shot = await send('Page.captureScreenshot', { format: 'jpeg', quality: 80 })
    if (!shot.result) { console.error('screenshot failed', JSON.stringify(shot.error)); continue }
    const name = `${path.replace(/[^a-z0-9]+/gi, '_').replace(/^_|_$/g, '') || 'home'}_${w}.jpg`
    writeFileSync(`${outDir}/${name}`, Buffer.from(shot.result.data, 'base64'))
    report.push({ path, width: w, overflow: m.sw > m.cw, scrollWidth: m.sw, brokenImages: m.broken, file: name })
  }
}
console.log(JSON.stringify(report, null, 1))
ws.close()
proc?.kill()

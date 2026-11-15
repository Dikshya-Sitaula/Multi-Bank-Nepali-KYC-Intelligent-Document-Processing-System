// Thin typed client for the FastAPI backend. Every value the UI shows comes from here.
const BASE = '/api/v1'
const TOKEN_KEY = 'kyc_token'

export function getToken(): string | null {
  try { return localStorage.getItem(TOKEN_KEY) } catch { return null }
}
export function setToken(t: string | null) {
  try { if (t) localStorage.setItem(TOKEN_KEY, t); else localStorage.removeItem(TOKEN_KEY) } catch { /* storage blocked */ }
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = getToken()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (res.status === 401 && path !== '/auth/login') {
    setToken(null)
    if (!location.pathname.startsWith('/login')) location.href = '/login'
  }
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail) } catch { /* not json */ }
    throw new ApiError(res.status, msg)
  }
  const ct = res.headers.get('content-type') || ''
  return (ct.includes('application/json') ? res.json() : res.text()) as Promise<T>
}

/** URL for an authenticated image (img tags cannot send headers, so the token goes in the query). */
export function fileUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined
  return `${BASE}/files/${path.split('/').map(encodeURIComponent).join('/')}?access_token=${encodeURIComponent(getToken() ?? '')}`
}

export async function download(path: string, filename: string) {
  const res = await fetch(`${BASE}${path}`, { headers: { Authorization: `Bearer ${getToken() ?? ''}` } })
  if (!res.ok) throw new ApiError(res.status, 'Download failed')
  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}

// ---- types (mirror the backend responses)
export type Health = {
  status: string; version: string; mode: string; mock_cv: boolean
  database: { name: string; ok: boolean; detail: string }
  worker: { name: string; ok: boolean; detail: string }
  components: { name: string; ok: boolean; detail: string }[]
  banners: string[]
}
export type Job = {
  id: number; job_type: string; status: string; progress: number; message: string | null
  stage_timings: Record<string, number> | null; document_id: number | null; error: string | null
  log?: { ts: string; msg: string }[] | null; created_at: string; finished_at: string | null
}
export type DocSummary = {
  id: number; public_id: string; display_name: string; status: string; template_id: string | null
  bank_name: string | null; template_confidence: number | null; page_count: number; created_at: string
  processing_seconds: number | null; field_counts: Record<string, number>; avg_ocr_confidence: number | null
}
export type CheckboxState = {
  option_id: string; box: number[]; inner: number[]; fill_ratio: number; baseline_ratio: number
  delta: number; state: string; confidence: number
}
export type Field = {
  id: number; field_id: string; display_name: string; section: string; field_type: string; priority: string | null
  group_id: string | null; row_index: number | null; applicant_index: number | null; page_id: number | null
  region_id: string | null; raw_text: string | null; normalized_value: string | null
  detection_confidence: number | null; ocr_confidence: number | null; engine: string | null; status: string
  validation_messages: string[]; crop_path: string | null; checkbox: CheckboxState[] | null; ink: number | null
  bbox: [number, number, number, number] | null
  verified_by: number | null; verified_at: string | null
}
export type PageInfo = {
  id: number; index: number; original_filename: string; original_path: string; processed_path: string | null
  width: number; height: number; quality: Record<string, number | null> | null; quality_warnings: string[]
  template_page_number: number | null; registration_confidence: number | null
  identification: { status: string; template_id: string | null; page_number: number | null; confidence: number; inliers: number } | null
  has_stages: boolean
}
export type DocDetail = DocSummary & { pages: PageInfo[]; fields: Field[]; jobs: Job[] }
export type Stage = {
  key: string; title: string; why: string; ms: number; applied: boolean; image: string | null
  params: Record<string, unknown>; metrics: Record<string, unknown>; data: Record<string, unknown>
}
export type StageRun = {
  params: Record<string, unknown>; stages: Stage[]; total_ms?: number
  identification?: { status: string; template_id: string | null; page_number: number | null; confidence: number; inliers: number; reason?: string | null }
  registration?: { overlap: number; aligned_image: string }
}
export type Paged<T> = { items: T[]; total: number; page: number; page_size: number }

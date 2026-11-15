import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export const pct = (v: number | null | undefined, digits = 0) =>
  v === null || v === undefined ? '—' : `${(v * 100).toFixed(digits)}%`

export const ms = (v: number | null | undefined) =>
  v === null || v === undefined ? '—' : v >= 1000 ? `${(v / 1000).toFixed(1)} s` : `${Math.round(v)} ms`

export function confColour(c: number | null | undefined) {
  if (c === null || c === undefined) return '#8b93a3'
  if (c >= 0.75) return '#34d399'
  if (c >= 0.45) return '#fbbf24'
  return '#f87171'
}

export const STATUS_LABEL: Record<string, string> = {
  auto_accepted: 'Auto-accepted', needs_review: 'Needs review', unreadable: 'Unreadable', empty: 'Empty',
  verified: 'Verified', uploaded: 'Uploaded', processing: 'Processing', failed: 'Failed',
}

export const STATUS_COLOUR: Record<string, string> = {
  auto_accepted: '#34d399', verified: '#22d3ee', needs_review: '#fbbf24', unreadable: '#f87171',
  empty: '#8b93a3', processing: '#22d3ee', uploaded: '#8b93a3', failed: '#f87171',
}

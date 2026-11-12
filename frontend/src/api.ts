import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
export const supabase = url && key ? createClient(url, key, { auth: { detectSessionInUrl: false } }) : null
const base = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

export async function api<T>(path: string, method = 'GET', body?: unknown): Promise<T> {
  if (!supabase) throw new Error('Supabase configuration is required for the private workspace.')
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Sign in to continue.')
  const response = await fetch(base + path, {
    method,
    headers: { Authorization: `Bearer ${session.access_token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(15000),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The API could not complete this request.')
  return data as T
}

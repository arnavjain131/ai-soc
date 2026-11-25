import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
export const supabase = url && key ? createClient(url, key, { auth: { detectSessionInUrl: false, flowType: 'pkce' } }) : null
const base = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) { super(message); this.status = status }
}

export async function api<T>(path: string, method = 'GET', body?: unknown, timeoutMs = 15000): Promise<T> {
  if (!supabase) throw new Error('Supabase configuration is required for the private workspace.')
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Sign in to continue.')
  const response = await fetch(base + path, {
    method,
    headers: { Authorization: `Bearer ${session.access_token}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
    signal: AbortSignal.timeout(timeoutMs),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new ApiError(response.status, typeof data.detail === 'string' ? data.detail : 'The API could not complete this request.')
  return data as T
}

export async function apiReport(path:string,format:'html'|'json',signal:AbortSignal):Promise<Blob> {
  if(!supabase)throw new Error('Supabase configuration is required for the private workspace.')
  const {data:{session}}=await supabase.auth.getSession()
  if(!session)throw new Error('Sign in to continue.')
  const response=await fetch(base+path,{headers:{Authorization:`Bearer ${session.access_token}`},
    cache:'no-store',redirect:'error',signal:AbortSignal.any([signal,AbortSignal.timeout(45000)])})
  if(!response.ok) {
    const data=await response.json().catch(()=>({}))
    throw new ApiError(response.status,typeof data.detail==='string'?data.detail:'Could not generate the incident report.')
  }
  const expected=format==='html'?'text/html':'application/json'
  if(!response.headers.get('Content-Type')?.toLowerCase().startsWith(expected))throw new Error('The server did not return the requested report format.')
  if(Number(response.headers.get('Content-Length'))>8*1024*1024)throw new Error('The report exceeds the download size limit.')
  const blob=await response.blob()
  if(blob.size>8*1024*1024)throw new Error('The report exceeds the download size limit.')
  return blob
}

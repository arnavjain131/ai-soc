import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { LockKeyhole, X } from 'lucide-react'
import { supabase } from './api'
import { completeRecovery, recoveryRedirect, validateNewPassword } from './accountRecovery'
import './accountAccess.css'

export function SignInDialog({ onClose, onSignedIn }: { onClose: () => void; onSignedIn: () => void }) {
  const [email, setEmail] = useState(''), [password, setPassword] = useState('')
  const [recover, setRecover] = useState(false), [busy, setBusy] = useState(false)
  const [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [cooldown, setCooldown] = useState(0)
  const submitting = useRef(false)
  useEffect(() => {
    if (!cooldown) return
    const timer = window.setInterval(() => setCooldown(value => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timer)
  }, [cooldown > 0])

  async function submit(event: FormEvent) {
    event.preventDefault()
    if (!supabase || submitting.current || (recover && cooldown)) return
    submitting.current = true; setBusy(true); setError(''); setNotice('')
    try {
      if (recover) {
        const { error: failure } = await supabase.auth.resetPasswordForEmail(email.trim(), { redirectTo: recoveryRedirect(window.location.origin) })
        setCooldown(60)
        if (failure) throw new Error('Recovery could not be requested. Wait before retrying, or contact your administrator.')
        setNotice('If this address can receive recovery mail, you will receive a link. Open the newest link in this same browser and browser profile. Delivery may take a few minutes.')
      } else {
        const { error: failure } = await supabase.auth.signInWithPassword({ email: email.trim(), password })
        if (failure) throw new Error('Sign-in failed. Check your credentials and email confirmation, or use password recovery.')
        setPassword(''); onSignedIn()
      }
    } catch (failure) {
      setError(failure instanceof Error && ['Recovery could not be requested. Wait before retrying, or contact your administrator.',
        'Sign-in failed. Check your credentials and email confirmation, or use password recovery.'].includes(failure.message)
        ? failure.message : 'The authentication service could not complete this request. Please try again later.')
    } finally { submitting.current = false; setBusy(false) }
  }

  return <div className="modal-backdrop" onClick={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section className="login panel" role="dialog" aria-modal="true" aria-labelledby="login-title" onKeyDown={event => { if (event.key === 'Escape' && !busy) onClose() }}>
      <button className="modal-close icon-button" disabled={busy} aria-label="Close sign in" onClick={onClose}><X size={20}/></button>
      <span className="brand-icon"><LockKeyhole size={24}/></span>
      <h2 id="login-title">{recover ? 'Recover your account' : 'Your analyst workspace'}</h2>
      <p className="muted">{recover ? 'Request a password reset for your existing account. Recovery does not grant workspace access.' : 'Sign in with an account approved by your administrator.'}</p>
      {!supabase && <p role="alert">Private authentication is not configured. The public demo remains available.</p>}
      <form onSubmit={submit}>
        <label htmlFor="email">Email address</label><input id="email" type="email" autoComplete="username" maxLength={254} required autoFocus value={email} onChange={event => setEmail(event.target.value)} disabled={busy}/>
        {!recover && <><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" required value={password} onChange={event => setPassword(event.target.value)} disabled={busy}/></>}
        {error && <p role="alert" className="login-error">{error}</p>}
        {notice && <p role="status" className="account-notice">{notice}</p>}
        <button className="primary" disabled={busy || !supabase || (recover && cooldown > 0)}>{busy ? 'Please wait…' : recover ? cooldown ? `Wait ${cooldown}s to retry` : 'Send recovery email' : 'Sign in'}</button>
      </form>
      <button className="quiet account-switch" disabled={busy} onClick={() => { setRecover(value => !value); setPassword(''); setError(''); setNotice('') }}>{recover ? 'Back to sign in' : 'Forgot your password?'}</button>
      <p className="small muted">No public registration. Ask your administrator for access.</p>
    </section>
  </div>
}

export function AccountRecovery({ exchange }: { exchange: () => Promise<boolean> }) {
  const [state, setState] = useState<'checking' | 'invalid' | 'ready' | 'done'>('checking')
  const [password, setPassword] = useState(''), [confirmation, setConfirmation] = useState('')
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [warning, setWarning] = useState('')
  const submitting = useRef(false)
  useEffect(() => {
    let active = true
    void exchange().then(valid => { if (active) setState(valid ? 'ready' : 'invalid') })
    return () => { active = false }
  }, [exchange])

  async function save(event: FormEvent) {
    event.preventDefault()
    if (!supabase || state !== 'ready' || submitting.current) return
    setError('')
    try { validateNewPassword(password, confirmation) }
    catch (failure) { setError((failure as Error).message); return }
    submitting.current = true; setBusy(true)
    try {
      const { signedOut } = await completeRecovery(supabase.auth, password, confirmation)
      setPassword(''); setConfirmation(''); setState('done')
      if (!signedOut) setWarning('Your password was updated, but session sign-out could not be confirmed. Sign out from any open sessions and contact your administrator if necessary.')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'The authentication service could not complete this request.') }
    finally { submitting.current = false; setBusy(false) }
  }

  return <main className="account-page"><section className="login panel">
    <span className="brand-icon"><LockKeyhole size={24}/></span><h1>Account recovery</h1>
    {state === 'checking' && <p role="status">Checking your recovery link…</p>}
    {state === 'invalid' && <><p role="alert">This recovery link could not be verified. It may have expired, already been used, or opened in a different browser. Request a new link from Analyst sign in → Forgot your password, and open it in that same browser and profile.</p><a href="/">Return to sign in</a></>}
    {state === 'ready' && <form onSubmit={save}>
      <p>Choose a unique password with 12–128 characters. Your administrator’s policy may require more.</p>
      <label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={password} disabled={busy} onChange={event => setPassword(event.target.value)}/>
      <label htmlFor="confirm-password">Confirm new password</label><input id="confirm-password" type="password" autoComplete="new-password" minLength={12} maxLength={128} required value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)}/>
      {error && <p role="alert" className="login-error">{error}</p>}<button className="primary" disabled={busy}>{busy ? 'Updating…' : 'Update password'}</button>
    </form>}
    {state === 'done' && <><p role="status">Your password was updated. Return to the website and sign in with your new password.</p>{warning && <p role="alert" className="login-error">{warning}</p>}<a href="/" aria-disabled={busy} onClick={event => { if (busy) event.preventDefault() }}>Return to sign in</a></>}
  </section></main>
}

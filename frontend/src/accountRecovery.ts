export const RECOVERY_PATH = '/auth/recovery'

export function recoveryCallback(url: string): { code: string | null; error: boolean } {
  const parsed = new URL(url)
  const codes = parsed.searchParams.getAll('code')
  return {
    code: parsed.pathname === RECOVERY_PATH && codes.length === 1 && codes[0].length <= 4096
      && codes[0].length > 0 && !parsed.hash && !parsed.searchParams.has('error') ? codes[0] : null,
    error: parsed.searchParams.has('error') || Boolean(parsed.hash),
  }
}

export function recoveryRedirect(origin: string): string {
  const url = new URL(origin)
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
    throw new Error('Recovery requires HTTPS or local development.')
  }
  return url.origin + RECOVERY_PATH
}

export function validateNewPassword(password: string, confirmation: string) {
  if (password.length < 12 || password.length > 128) throw new Error('Use a password with 12–128 characters.')
  if (password !== confirmation) throw new Error('The passwords do not match.')
}

type Exchange = (code: string) => Promise<{
  data: { session: unknown; redirectType?: string | null }; error: unknown
}>

// One exchange per page, including React StrictMode's effect replay. An existing
// session alone never enables this password form, nor does an implicit URL token.
export function recoveryExchange(exchange: Exchange, callback: ReturnType<typeof recoveryCallback>) {
  let pending: Promise<boolean> | undefined
  return () => pending ??= (async () => {
    if (!callback.code || callback.error) return false
    try {
      const { data, error } = await exchange(callback.code)
      return !error && Boolean(data.session) && data.redirectType === 'recovery'
    } catch { return false }
  })()
}

type RecoveryAuth = {
  updateUser: (attributes: { password: string }) => Promise<{ error: unknown }>
  signOut: (options: { scope: 'global' }) => Promise<{ error: unknown }>
}

export async function completeRecovery(auth: RecoveryAuth, password: string, confirmation: string) {
  validateNewPassword(password, confirmation)
  try {
    const { error } = await auth.updateUser({ password })
    if (error) throw new Error('update_failed')
  } catch {
    throw new Error('Password could not be updated. Check your administrator’s password policy. If the link expired, request a new one.')
  }
  // Password change already succeeded: a sign-out failure must never suggest
  // submitting the password change again or falsely claim sessions were ended.
  try { return { signedOut: !(await auth.signOut({ scope: 'global' })).error } }
  catch { return { signedOut: false } }
}

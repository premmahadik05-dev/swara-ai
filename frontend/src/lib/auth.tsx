import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { api, ApiError, clearApiCache, csrfToken, setUnauthorizedHandler } from '../api/client'
import type { AuthUser, SignUpResult } from '../types'

type Status = 'loading' | 'in' | 'out'
export interface AuthState {
  status: Status
  user: AuthUser | null
  /** why the person is signed out, when it was not their own choice */
  notice: 'expired' | null
  /** set when the server could not be reached while checking for a session */
  bootError: string | null
  signIn: (email: string, password: string, remember: boolean) => Promise<AuthUser>
  signUp: (b: { full_name: string; email: string; password: string; confirm_password: string; accept_terms: boolean }) => Promise<SignUpResult>
  signOut: () => Promise<void>
  setUser: (u: AuthUser) => void
  clearNotice: () => void
}

export const AuthContext = createContext<AuthState | null>(null)
const Ctx = AuthContext

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status>('loading')
  const [user, setUserState] = useState<AuthUser | null>(null)
  const [notice, setNotice] = useState<'expired' | null>(null)
  const [bootError, setBootError] = useState<string | null>(null)
  const statusRef = useRef<Status>('loading')
  statusRef.current = status

  const enter = useCallback((u: AuthUser, csrf: string) => {
    csrfToken.set(csrf)
    clearApiCache()
    setUserState(u)
    setNotice(null)
    setBootError(null)
    setStatus('in')
  }, [])
  const leave = useCallback((why: 'expired' | null) => {
    csrfToken.set(null)
    clearApiCache()
    setUserState(null)
    setNotice(why)
    setStatus('out')
  }, [])

  useEffect(() => {
    let alive = true
    api.authSession()
      .then((s) => { if (!alive) return; if (s.authenticated) enter(s.user, s.csrf_token); else leave(null) })
      .catch((e: ApiError) => { if (!alive) return; setBootError(e.message); leave(null) })
    return () => { alive = false }
  }, [enter, leave])

  // Any protected call that comes back 401 means the session has ended (expired, signed out elsewhere, account turned off).
  useEffect(() => {
    setUnauthorizedHandler(() => { if (statusRef.current === 'in') leave('expired') })
    return () => setUnauthorizedHandler(null)
  }, [leave])

  const value = useMemo<AuthState>(() => ({
    status, user, notice, bootError,
    signIn: async (email, password, remember) => {
      const r = await api.signIn({ email, password, remember })
      enter(r.user, r.csrf_token)
      return r.user
    },
    signUp: async (b) => {
      const r = await api.signUp(b)
      if (r.user && r.csrf_token) enter(r.user, r.csrf_token)
      return r
    },
    signOut: async () => {
      try { await api.signOut() } catch { /* the cookie is cleared server-side when it can be; either way this device is done */ }
      leave(null)
    },
    setUser: (u) => setUserState(u),
    clearNotice: () => setNotice(null),
  }), [status, user, notice, bootError, enter, leave])

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export function useAuth(): AuthState {
  const v = useContext(Ctx)
  if (!v) throw new Error('useAuth must be used inside <AuthProvider>')
  return v
}

/** Only same-site paths are honoured after sign-in, so a crafted ?next= link cannot send someone to another website. */
export function safeNext(next: string | null | undefined, fallback = '/dashboard'): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return fallback
  if (/^\/(sign-in|sign-up|forgot-password|reset-password|verify-email)(\/|\?|$)/.test(next)) return fallback
  return next
}

/** Sign out, then land on the public home page. The navigation comes FIRST on purpose: the app routes sit inside RequireAuth, which sends a
 *  signed-out visitor to /sign-in?next=..., and if the session turned "out" before this navigation ran, which of the two redirects won
 *  was a race (it flipped when react-router moved to v7). A deliberate sign-out should always end on the home page. */
export function useSignOut() {
  const { signOut } = useAuth()
  const nav = useNavigate()
  return useCallback(async () => { nav('/', { replace: true }); await signOut() }, [nav, signOut])
}

/** Wraps every page that needs a signed-in person. */
export function RequireAuth() {
  const a = useAuth()
  const loc = useLocation()
  if (a.status === 'loading') return <div className="boot" role="status" aria-live="polite"><span className="spinner" aria-hidden /> Checking your session…</div>
  if (a.status === 'out') {
    const next = loc.pathname + loc.search
    return <Navigate to={`/sign-in?next=${encodeURIComponent(next)}`} replace state={{ expired: a.notice === 'expired' }} />
  }
  return <Outlet />
}

/** True for the shop owner. Staff can look and take orders, but the server refuses changes to stock, prices, customers and order status. */
export function useIsOwner(): boolean {
  return useAuth().user?.role === 'owner'
}

/** Owner-only screens. Staff get an explanation rather than a blank page. */
export function OwnerOnly({ children }: { children: ReactNode }) {
  const a = useAuth()
  if (a.user?.role === 'owner') return <>{children}</>
  return null
}

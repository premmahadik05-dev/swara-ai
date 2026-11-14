import type { ReactNode } from 'react'
import { AuthContext, type AuthState } from '../lib/auth'
import type { AuthUser } from '../types'

export const OWNER_USER: AuthUser = {
  id: 1, email: 'ramesh@example.com', full_name: 'Ramesh Patel', role: 'owner', email_verified: false,
  created_at: '2026-11-01T09:00:00Z', last_login_at: '2026-11-10T08:30:00Z', preferences: {},
}
export const STAFF_USER: AuthUser = { ...OWNER_USER, id: 2, email: 'meena@example.com', full_name: 'Meena Shah', role: 'staff' }

/** Renders children as if this person were signed in. Pass user={null} for a visitor. */
export function TestAuth({ user = OWNER_USER, children, over = {} }: { user?: AuthUser | null; children: ReactNode; over?: Partial<AuthState> }) {
  const value: AuthState = {
    status: user ? 'in' : 'out', user, notice: null, bootError: null,
    signIn: async () => { throw new Error('not wired in this test') }, signUp: async () => { throw new Error('not wired in this test') },
    signOut: async () => undefined, setUser: () => undefined, clearNotice: () => undefined, ...over,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

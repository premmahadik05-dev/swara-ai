import { ApiError } from '../../api/client'

export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/

export type FieldName = 'name' | 'email' | 'password' | 'confirm' | 'terms'

/** Which form field a server error belongs to, so the message appears next to it. */
export function fieldForCode(code: string): FieldName | null {
  switch (code) {
    case 'BAD_NAME': return 'name'
    case 'BAD_EMAIL': case 'EMAIL_TAKEN': return 'email'
    case 'WEAK_PASSWORD': return 'password'
    case 'PASSWORD_MISMATCH': return 'confirm'
    case 'TERMS_REQUIRED': return 'terms'
    default: return null
  }
}

export const errMessage = (e: unknown): string => (e instanceof ApiError || e instanceof Error ? e.message : 'Something went wrong. Try again.')
export const errCode = (e: unknown): string => (e instanceof ApiError ? e.code : '')

/** Guidance shown while a person types a password. The server enforces the real rules (backend/app/services/passwords.py);
 *  this only explains them early. The two are kept in step by tests on both sides. */
export const MIN_LEN = 10
export const MAX_LEN = 128

export interface Rule { id: string; label: string; ok: boolean }

export function strength(pw: string): number {
  if (!pw) return 0
  const pools = [/[a-z]/, /[A-Z]/, /\d/, /[^A-Za-z0-9]/].filter((r) => r.test(pw)).length
  const score = Number(pw.length >= 10) + Number(pw.length >= 14) + Number(pools >= 3) + Number(pools >= 4 || pw.length >= 20)
  return Math.min(score, 4)
}

export const STRENGTH_LABEL = ['Too short', 'Weak', 'Fair', 'Good', 'Strong'] as const

export function rules(pw: string, ctx: { email?: string; name?: string } = {}): Rule[] {
  const local = (ctx.email ?? '').split('@')[0].toLowerCase()
  return [
    { id: 'len', label: `At least ${MIN_LEN} characters`, ok: pw.length >= MIN_LEN },
    { id: 'trim', label: 'No spaces at the start or end', ok: pw === pw.trim() && pw.length > 0 },
    { id: 'mail', label: 'Does not contain your e-mail name', ok: !(local.length >= 4 && pw.toLowerCase().includes(local)) },
    { id: 'mix', label: 'Mixes letters with numbers or symbols (recommended)', ok: /[A-Za-z]/.test(pw) && /[^A-Za-z]/.test(pw) },
  ]
}

/** First message for an obviously unusable password, or null. Does not replace the server's check. */
export function firstProblem(pw: string, ctx: { email?: string; name?: string } = {}): string | null {
  if (pw.length < MIN_LEN) return `Use at least ${MIN_LEN} characters.`
  if (pw.length > MAX_LEN) return `Use at most ${MAX_LEN} characters.`
  if (pw !== pw.trim()) return 'Remove spaces at the start or end.'
  const r = rules(pw, ctx).find((x) => x.id === 'mail' && !x.ok)
  return r ? 'Do not include your e-mail name in the password.' : null
}

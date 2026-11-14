import { describe, expect, it } from 'vitest'
import { firstProblem, rules, strength } from './password'

describe('password guidance', () => {
  it('rates obvious cases in order', () => {
    expect(strength('')).toBe(0)
    expect(strength('abcdefghij')).toBeLessThan(strength('Abcdefghij1!x'))
    expect(strength('Abcdefghij1!x')).toBeLessThanOrEqual(strength('Abcdefghij1!x-and-longer-still'))
    expect(strength('Abcdefghij1!x-and-longer-still')).toBe(4)
  })
  it('matches the server rules that can be checked without a word list', () => {
    expect(firstProblem('short1!')).toMatch(/at least 10/)
    expect(firstProblem('x'.repeat(129))).toMatch(/at most 128/)
    expect(firstProblem(' padded-pass-123')).toMatch(/spaces/)
    expect(firstProblem('xx-ramesh-xx-1!', { email: 'ramesh@example.com' })).toMatch(/e-mail name/)
    expect(firstProblem('Correct-Horse-9!', { email: 'ramesh@example.com' })).toBeNull()
    expect(firstProblem('abc-xyz-123-QQ', { email: 'ab@example.com' })).toBeNull()      // short local parts are not matched
  })
  it('lists each rule with whether it holds', () => {
    const r = rules('Correct-Horse-9!', { email: 'ramesh@example.com' })
    expect(r.every((x) => x.ok)).toBe(true)
    expect(rules('abc', {}).find((x) => x.id === 'len')?.ok).toBe(false)
  })
})

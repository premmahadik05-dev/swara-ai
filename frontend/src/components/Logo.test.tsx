import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Logo, LogoMark } from './Logo'

describe('Logo', () => {
  it('is announced once as "SWARA AI" when it stands alone', () => {
    render(<Logo height={40} />)
    expect(screen.getByRole('img', { name: 'SWARA AI' })).toBeInTheDocument()
  })

  it('is hidden from assistive tech when a link already carries the name', () => {
    const { container } = render(<a href="/" aria-label="SWARA AI, home"><Logo decorative height={40} /><LogoMark decorative size={30} /></a>)
    expect(screen.queryByRole('img')).toBeNull()
    expect(container.querySelectorAll('svg[aria-hidden="true"]')).toHaveLength(2)
  })

  it('keeps the shape: three ribbons for the full mark, two for the compact one, and the name SWARA AI as outlines', () => {
    const { container, rerender } = render(<LogoMark size={64} />)
    expect(container.querySelectorAll('g > path')).toHaveLength(3)
    rerender(<LogoMark size={32} compact />)
    expect(container.querySelectorAll('g > path')).toHaveLength(2)
    rerender(<Logo height={40} />)
    expect(container.querySelectorAll('svg > path')).toHaveLength(2)      // the words SWARA and AI, as outlines: no font needed
  })

  it('takes its colours from theme tokens, so it is right on the white and ivory surfaces', () => {
    const { container } = render(<Logo height={40} />)
    const stops = [...container.querySelectorAll('stop')].map((s) => (s as SVGStopElement).style.stopColor)
    expect(stops).toEqual(['var(--logo-hi)', 'var(--logo-mid)', 'var(--logo-lo)'])
    const words = [...container.querySelectorAll('svg > path')]
    expect(words).toHaveLength(2)
    expect(words.every((w) => w.getAttribute('fill') === 'var(--text)')).toBe(true)   // one colour: it reads as one name
  })

  it('gives each instance its own gradient id, so two logos on one page do not share or break each other', () => {
    const { container } = render(<><Logo height={40} /><LogoMark size={30} /></>)
    const ids = [...container.querySelectorAll('linearGradient')].map((g) => g.id)
    expect(new Set(ids).size).toBe(2)
    expect(ids.every((id) => /^[A-Za-z][A-Za-z0-9]*$/.test(id))).toBe(true)   // no ":" from useId, which would break url(#id)
  })
})

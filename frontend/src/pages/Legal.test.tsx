import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import { Privacy, Terms } from './Legal'
import NotFound from './NotFound'

const at = (el: React.ReactNode) => render(<MemoryRouter>{el}</MemoryRouter>)

describe('Legal pages', () => {
  it('Terms: one h1, a main landmark, a way home, and an honest note that it is a template', () => {
    at(<Terms />)
    expect(screen.getByRole('heading', { level: 1, name: 'Terms of Use' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Back to home' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('note')).toHaveTextContent(/not legal advice/)
    expect(document.title).toBe('Terms of Use · SWARA AI')
  })
  it('Privacy: says what is stored and where voice audio goes, without promising what the software does not do', () => {
    at(<Privacy />)
    expect(screen.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeInTheDocument()
    expect(screen.getByRole('main')).toHaveTextContent(/Gnani/)
    expect(screen.getByRole('main')).toHaveTextContent(/password/i)
    expect(document.title).toBe('Privacy Policy · SWARA AI')
  })
})

describe('Not found', () => {
  it('explains the problem and offers two ways out', () => {
    at(<NotFound />)
    expect(screen.getByRole('heading', { level: 1, name: 'This page does not exist' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Go to the home page' })).toHaveAttribute('href', '/')
    expect(screen.getByRole('link', { name: 'Open the dashboard' })).toHaveAttribute('href', '/dashboard')
  })
})

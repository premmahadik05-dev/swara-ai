import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import Landing from './Landing'
import { FAQ, FLOW, LANGUAGES, NAV, NEW_LANGUAGES, SECURITY, SECURITY_LIMITS, SHOWCASE, SPECIMEN, STACK, TECH, VARIANTS, WHY } from './landing/content'
import { BRAND } from '../lib/brand'
import { OWNER_USER, TestAuth } from '../test/auth'
import { err, mockRoutes, turn } from '../test/fixtures'
import type { AuthUser } from '../types'

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear() })
beforeEach(() => {
  vi.stubGlobal('matchMedia', (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, dispatchEvent: () => false, onchange: null }))
})

const PARSE = { 'POST /api/text/parse': turn() }
function renderIt(user: AuthUser | null = null, routes: Record<string, unknown> = PARSE) {
  const m = mockRoutes(routes)
  const view = render(<MemoryRouter><TestAuth user={user}><Landing /></TestAuth></MemoryRouter>)
  return { ...view, ...m }
}

describe('Landing: message and calls to action', () => {
  it('leads with the headline and the lead from the brief, with the two required calls to action', () => {
    renderIt()
    const h1 = screen.getByRole('heading', { level: 1 })
    expect(h1.textContent?.replace(/\s+/g, ' ').trim()).toBe('Commerce that understands every voice.')
    expect(screen.getByText(BRAND.lead)).toBeInTheDocument()
    expect(BRAND.lead).toBe('An intelligent multilingual voice-commerce platform helping India\u2019s kirana stores simplify ordering, inventory, and everyday business operations through natural conversations.')
    const hero = within(screen.getByRole('region', { name: /Commerce that understands every voice/ }))
    expect(hero.getByRole('link', { name: 'Get Started Free' })).toHaveAttribute('href', '/sign-up')
    expect(hero.getByRole('link', { name: 'Explore the Platform' })).toHaveAttribute('href', '#product')
    // the picture that decides the page's loading time is fetched first (React 18 only passes the lowercase spelling through without a warning)
    expect(hero.getByRole('img')).toHaveAttribute('fetchpriority', 'high')
  })

  it('names all eleven language choices in their own scripts under the headline, without calling them verified', () => {
    renderIt()
    const row = screen.getByLabelText(/^Languages: Gujarati, Hindi, English, Hinglish, Marathi/)
    expect([...row.querySelectorAll('span')].map((x) => x.textContent)).toEqual([...LANGUAGES, ...NEW_LANGUAGES].map((l) => l.script))
    expect(row.textContent).not.toMatch(/verified|supported|live/i)
  })

  it('keeps the brand tagline in the footer and has an About section with the official wording', () => {
    renderIt()
    expect(within(screen.getByRole('contentinfo')).getByText('Every Voice. Smarter Commerce.')).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'About SWARA AI' })).toBeInTheDocument()
    expect(screen.getByText(/^SWARA AI is an intelligent, multilingual, voice-powered commerce platform/)).toBeInTheDocument()
    expect(document.title).toBe('SWARA AI: Every Voice. Smarter Commerce.')
  })

  it('never shows the previous product name', () => {
    const { container } = renderIt()
    expect(container.innerHTML).not.toMatch(/dukaan\s*mitra/i)
  })

  it('shows the dashboard shortcut instead of sign-up buttons to someone who is already signed in', () => {
    renderIt(OWNER_USER)
    expect(screen.getAllByRole('link', { name: 'Open dashboard' }).length).toBeGreaterThanOrEqual(2)
    expect(screen.queryByRole('link', { name: 'Get Started Free' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'Sign In' })).toBeNull()
  })
})

describe('Landing: navigation', () => {
  it('has every required section link and the two account buttons in the top bar', () => {
    renderIt()
    const bar = within(screen.getByRole('navigation', { name: 'Sections of this page' }))
    expect(NAV.map((n) => n.label)).toEqual(['Product', 'How it works', 'Languages', 'Technology', 'Security', 'Contact'])
    for (const n of NAV) expect(bar.getByRole('link', { name: n.label })).toHaveAttribute('href', n.href)
    const top = within(screen.getByRole('banner'))
    expect(top.getByRole('link', { name: 'Sign In' })).toHaveAttribute('href', '/sign-in')
    expect(top.getByRole('link', { name: 'Get Started Free' })).toHaveAttribute('href', '/sign-up')
  })

  it('has no dead links: every in-page anchor points at an element that exists, every route link at a real route', () => {
    const { container } = renderIt()
    const routes = new Set(['/', '/sign-in', '/sign-up', '/terms', '/privacy', '/dashboard', '/account', '/docs'])
    const anchors = [...container.querySelectorAll('a[href]')]
    expect(anchors.length).toBeGreaterThan(20)
    for (const a of anchors) {
      const href = a.getAttribute('href')!
      if (href.startsWith('#')) expect(container.querySelector(href), `anchor ${href}`).not.toBeNull()
      else if (href.startsWith('/') && !href.startsWith('/shots/')) expect(routes.has(href), `route ${href}`).toBe(true)
    }
    for (const b of container.querySelectorAll('button')) expect((b.textContent ?? '').trim() || b.getAttribute('aria-label'), 'button needs a name').toBeTruthy()
  })

  it('opens a menu on small screens, lists the same sections, and closes on Escape with focus back on the button', async () => {
    renderIt()
    const btn = screen.getByRole('button', { name: 'Open menu' })
    expect(btn).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(btn)
    expect(screen.getByRole('button', { name: 'Close menu' })).toHaveAttribute('aria-expanded', 'true')
    const menu = within(screen.getByRole('navigation', { name: 'Sections of this page (menu)' }))
    for (const n of NAV) expect(menu.getByRole('link', { name: n.label })).toBeInTheDocument()
    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('navigation', { name: 'Sections of this page (menu)' })).toBeNull()
    expect(screen.getByRole('button', { name: 'Open menu' })).toHaveFocus()
  })

  it('has a skip link and one main landmark', () => {
    renderIt()
    expect(screen.getByRole('link', { name: 'Skip to content' })).toHaveAttribute('href', '#main')
    expect(screen.getAllByRole('main')).toHaveLength(1)
  })
})

describe('Landing: content that must be there, and content that must not', () => {
  it('has every section the brief asks for, each with a heading', () => {
    renderIt()
    for (const h of [/About SWARA AI/, /Everything a counter needs/, /How it works/, /Eleven ways to place the same order/, /Technology, and what is not built/,
      /Security and trust/, /Why SWARA AI/, /Questions, answered/, /Talk to us/]) {
      expect(screen.getByRole('heading', { level: 2, name: h })).toBeInTheDocument()
    }
    expect(screen.getAllByRole('listitem').length).toBeGreaterThan(30)
  })

  it('has a sensible heading outline: one h1, and no level is skipped', () => {
    const { container } = renderIt()
    const levels = [...container.querySelectorAll('h1,h2,h3,h4')].map((h) => Number(h.tagName[1]))
    expect(levels.filter((l) => l === 1)).toHaveLength(1)
    levels.reduce((prev, l) => { expect(l - prev, `heading jump ${prev} -> ${l}`).toBeLessThanOrEqual(1); return l }, 1)
  })

  it('contains no invented testimonials, customer counts, partners, revenue or speed claims, and no emoji', () => {
    const { container } = renderIt()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/testimonial|trusted by|as seen|join(ed)? (over |more than )?\d|\d[\d,]*\+?\s*(happy |active )?(customers|stores|shops|users|businesses|merchants)|\d+\s*%|faster than|\bx faster\b|ROI|case study/i)
    expect(text).not.toMatch(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B50}\u{2B55}\u{FE0F}]/u)       // emoji and pictograph blocks (the (c) sign and the rupee sign are not in them)
  })

  it('says plainly what is built, what needs credentials, and what is not built', () => {
    renderIt()
    const sec = within(screen.getByRole('region', { name: /Technology, and what is not built/ }))
    expect(sec.getByRole('heading', { name: 'Working in this release' })).toBeInTheDocument()
    expect(sec.getByRole('heading', { name: 'Works once you add credentials' })).toBeInTheDocument()
    const notBuilt = within(sec.getByRole('heading', { name: 'Not built' }).closest('div')!)
    for (const t of TECH.filter((x) => x.status === 'none')) expect(notBuilt.getByText(t.area)).toBeInTheDocument()
    expect(notBuilt.getByText('Evon')).toBeInTheDocument()
    expect(sec.getByText(/local stand-in for Gnani, not the live service/)).toBeInTheDocument()
  })

  it('shows each language in its own script, tagged with the right lang attribute', () => {
    const { container } = renderIt()
    for (const l of LANGUAGES) {
      const el = screen.getByText(l.script, { selector: '.lp-script' })
      expect(el).toHaveAttribute('lang', l.lang)
    }
    expect(container.querySelector('.lp-script[lang="gu"]')?.textContent).toBe('ગુજરાતી')
    expect(container.querySelector('.lp-script[lang="hi"]')?.textContent).toBe('हिन्दी')
  })

  it('lists the seven newer languages apart from the four proven ones, and says plainly they are new and unreviewed', () => {
    const { container } = renderIt()
    expect(NEW_LANGUAGES.map((l) => l.name)).toEqual(['Marathi', 'Bengali', 'Tamil', 'Telugu', 'Kannada', 'Malayalam', 'Punjabi'])
    const grid = within(screen.getByRole('list', { name: 'New languages' }))
    expect(grid.getAllByRole('listitem')).toHaveLength(7)
    for (const l of NEW_LANGUAGES) expect(grid.getByText(l.script, { selector: '.lp-script' })).toHaveAttribute('lang', l.lang)
    expect(container.querySelector('#languages')?.textContent).toMatch(/no native speaker has reviewed them/)
    expect(container.querySelector('#languages')?.textContent).toMatch(/not been checked against real recordings/)
  })

  it('does not claim that the new languages are verified, tested live or fully supported', () => {
    const { container } = renderIt()
    const text = container.textContent ?? ''
    expect(text).not.toMatch(/verified live|live[- ]verified|all 10 languages|all eleven languages work|fully supported/i)
    expect(text).not.toMatch(/More Indian languages are not supported yet/)
    expect(FAQ.find((f) => f.q === 'Which languages does it understand?')!.a).toMatch(/not been reviewed by native speakers/)
  })

  it('has a native FAQ that works without scripts', () => {
    const { container } = renderIt()
    const details = container.querySelectorAll('.lp-faq details')
    expect(details).toHaveLength(FAQ.length)
    for (const d of details) expect(d.firstElementChild?.tagName).toBe('SUMMARY')
    expect(screen.getByText('Do I need a Gnani API key?')).toBeInTheDocument()
  })

  it('footer has the legal links and the account links', () => {
    renderIt()
    const foot = within(screen.getByRole('contentinfo'))
    expect(foot.getByRole('link', { name: 'Terms of Use' })).toHaveAttribute('href', '/terms')
    expect(foot.getByRole('link', { name: 'Privacy Policy' })).toHaveAttribute('href', '/privacy')
    expect(foot.getByRole('link', { name: 'Sign In' })).toHaveAttribute('href', '/sign-in')
    expect(foot.getByRole('link', { name: 'Get Started Free' })).toHaveAttribute('href', '/sign-up')
  })

  it('credits Gnani for the speech models and says it is not affiliated', () => {
    renderIt()
    const foot = screen.getByRole('contentinfo')
    expect(foot).toHaveTextContent(/Gnani\.ai Prisma/)
    expect(foot).toHaveTextContent(/Gnani\.ai Timbre/)
    expect(foot).toHaveTextContent(/not affiliated with or endorsed by Gnani\.ai/)
  })
})

describe('Landing: pictures', () => {
  it('every picture has a description and a size (no layout jump), and only the first one loads eagerly', () => {
    const { container } = renderIt()
    const imgs = [...container.querySelectorAll('img')]
    expect(imgs.length).toBeGreaterThanOrEqual(2)
    for (const i of imgs) {
      expect(i.getAttribute('alt')!.length).toBeGreaterThan(20)
      expect(i.getAttribute('width')).toBeTruthy()
      expect(i.getAttribute('height')).toBeTruthy()
      expect(i.getAttribute('src')).toMatch(/^\/shots\/[a-z-]+\.webp$/)
    }
    expect(imgs[0].getAttribute('loading')).not.toBe('lazy')
    expect(imgs.slice(1).every((i) => i.getAttribute('loading') === 'lazy')).toBe(true)
    expect(screen.getAllByText(/generated demo data/).length).toBeGreaterThanOrEqual(2)       // the screenshots say what they show
  })

})

describe('Landing: product showcase', () => {
  const TITLES = ['Multilingual voice ordering', 'Intelligent product recognition', 'Smart inventory management', 'Automated order processing', 'Business analytics and insights']

  it('shows the five product areas of the brief, in order, each as a labelled article with its own heading', () => {
    renderIt()
    expect(Object.values(SHOWCASE).map((x) => x.title)).toEqual(TITLES)
    const product = within(document.getElementById('product')!)
    const articles = product.getAllByRole('article')
    expect(articles).toHaveLength(5)
    expect(articles.map((a) => a.getAttribute('aria-labelledby'))).toEqual(['sw-voice-h', 'sw-recog-h', 'sw-stock-h', 'sw-orders-h', 'sw-numbers-h'])
    expect(product.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(TITLES)
  })

  it('gives the five areas different compositions rather than one repeated card', () => {
    const { container } = renderIt()
    const classes = [...container.querySelectorAll('#product article')].map((a) => [...a.classList].find((c) => c.startsWith('sw-') && c !== 'sw-grid'))
    expect(new Set(classes).size).toBe(5)
  })

  it('the voice area is typeset sample sentences, marked as samples and not a recording, in the right language each', () => {
    const { container } = renderIt()
    const list = within(screen.getByRole('list', { name: 'Sample sentences' }))
    expect(list.getAllByRole('listitem')).toHaveLength(SPECIMEN.length)
    for (const s of SPECIMEN) {
      const p = container.querySelector(`.spec p[lang="${s.lang}"]`)
      expect(p?.textContent).toBe(s.parts.map((x) => x.t).join(''))
    }
    // what is underlined is exactly the quantity and the item, checked against the running parser when the page was written
    expect([...container.querySelectorAll('.spec li:nth-child(3) mark')].map((m) => m.textContent)).toEqual(['2 kilo chawal', '1 litre doodh'])
    expect(screen.getByText(/Sample sentences, not a recording/)).toBeInTheDocument()
  })

  it('the recognition area shows four spellings that meet at one item', () => {
    renderIt()
    const list = within(screen.getByRole('list', { name: 'Four ways to name one item' }))
    expect(list.getAllByRole('listitem').map((li) => li.querySelector('span')?.textContent)).toEqual(VARIANTS.map((v) => v.text))
    expect(VARIANTS.map((v) => v.text)).toEqual(['doodh', 'દૂધ', 'दूध', 'milk'])
    expect(document.querySelector('.variants-item')?.textContent).toBe('Milk')
  })

  it('the screenshots are of the running app and are said to be generated demo data', () => {
    const { container } = renderIt()
    const shown = [...container.querySelectorAll('#product img')].map((i) => i.getAttribute('src'))
    expect(shown).toEqual(['/shots/inventory.webp', '/shots/order-desk.webp', '/shots/orders.webp', '/shots/analytics.webp'])
    expect(container.querySelector('.sw-cap')?.textContent).toMatch(/generated demo data/)
    for (const f of container.querySelectorAll('#product figcaption')) expect(f.textContent).toMatch(/generated demo data|not a recording|Each of the four spellings/)
  })

  it('what it says about each area is limited to things the code does (no figures, no comparisons)', () => {
    const text = JSON.stringify(SHOWCASE)
    expect(text).not.toMatch(/\d+\s*%|\bfaster\b|\bbest-in-class\b|world-class|AI-powered|revolution|seamless|cutting-edge|unlock|supercharge/i)
  })
})

describe('Landing: language showcase', () => {
  it('lists all eleven, in two labelled groups: four since the first release and seven new ones', () => {
    renderIt()
    expect(within(screen.getByRole('list', { name: 'Languages' })).getAllByRole('listitem')).toHaveLength(4)
    expect(within(screen.getByRole('list', { name: 'New languages' })).getAllByRole('listitem')).toHaveLength(7)
    expect(screen.getByRole('heading', { level: 3, name: 'In use since the first release' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 3, name: 'New in this release' })).toBeInTheDocument()
  })

  it('says what has been checked: the rules are unit-tested, no language has been checked against the live service', () => {
    const { container } = renderIt()
    const status = container.querySelector('.lp-status')!.textContent!
    expect(status).toMatch(/unit-tested/)
    expect(status).toMatch(/none of\s+them has been checked against Gnani.s live service/)
    expect(container.querySelector('#languages')?.textContent).toMatch(/Other Indian languages are not supported/)
  })

  it('writes each sample sentence in its own language', () => {
    const { container } = renderIt()
    for (const l of [...LANGUAGES, ...NEW_LANGUAGES]) {
      const p = [...container.querySelectorAll('.lp-sample')].find((x) => x.textContent === `\u201c${l.sample}\u201d`)
      expect(p, l.name).toBeTruthy()
      expect(p).toHaveAttribute('lang', l.lang)
    }
  })
})

describe('Landing: technology', () => {
  it('shows how the four parts connect, and lists the stack that is really used', () => {
    const { container } = renderIt()
    const flow = within(screen.getByRole('list', { name: 'How the parts connect' }))
    expect(flow.getAllByRole('listitem').map((li) => li.querySelector('b')?.textContent)).toEqual(FLOW.map((f) => f.title))
    expect(FLOW.map((f) => f.title)).toEqual(['The browser', 'Your server', 'Your database', 'Gnani speech services'])
    const stack = container.querySelector('.lp-stack')!
    expect([...stack.querySelectorAll('dt')].map((d) => d.textContent)).toEqual(STACK.map((s) => s.part))
    expect(stack.textContent).toMatch(/Gnani Prisma v2\.5/)
    expect(stack.textContent).toMatch(/Gnani Timbre v2\.5/)
    expect(stack.textContent).toMatch(/not a generative model/)
  })

  it('says that the key stays on the server', () => {
    renderIt()
    expect(screen.getByText(/The Gnani key lives here and never reaches the browser/)).toBeInTheDocument()
  })
})

describe('Landing: why', () => {
  it('has the four reasons, each stated as something the product does', () => {
    renderIt()
    const sec = document.getElementById('why')!
    expect([...sec.querySelectorAll('dt')].map((d) => d.textContent)).toEqual(WHY.map((w) => w.title))
    expect(WHY).toHaveLength(4)
  })
})

describe('Landing: live language demo', () => {
  it('parses the pre-filled example against the real endpoint and writes it onto the bill', async () => {
    const { calls } = renderIt()
    await waitFor(() => expect(screen.getByText('Rice')).toBeInTheDocument(), { timeout: 3000 })
    const parse = calls.find((c) => c.url === '/api/text/parse')!
    expect(JSON.parse(parse.body!).text).toMatch(/chawal/)
    expect(screen.getByText('₹172')).toBeInTheDocument()
    expect(screen.getByText('intent: add')).toBeInTheDocument()
  })

  it('fills the four-step strip from the real answer, and labels the demo as a demonstration with no audio', async () => {
    renderIt()
    const strip = screen.getByRole('list', { name: 'What the language engine did' })
    expect(within(strip).getAllByRole('listitem').map((li) => li.querySelector('b')?.textContent)).toEqual(['Heard', 'Products found', 'Stock checked', 'Bill prepared'])
    expect(strip).toHaveTextContent('Waiting for a sentence')                       // before the first answer it says so instead of showing a made-up result
    await waitFor(() => expect(strip).toHaveTextContent('Read as Hinglish'), { timeout: 3000 })
    expect(strip).toHaveTextContent('2 products matched')
    expect(strip).toHaveTextContent('Enough in stock')
    expect(strip).toHaveTextContent('Added up, ready to read back')
    expect(screen.getByText(/A demonstration: typed text only, so no audio is involved/)).toBeInTheDocument()
    expect(screen.getByText(/Nothing is saved and no stock is reserved/)).toBeInTheDocument()
  })

  it('names the item that is short, from the real stock figure, when a customer asks for more than is on the shelf', async () => {
    const short = { ...turn(), cart: { ...turn().cart, lines: [{ ...turn().cart.lines[0], qty: '50', in_stock: 3 }] } }
    renderIt(null, { 'POST /api/text/parse': short })
    await waitFor(() => expect(screen.getByRole('list', { name: 'What the language engine did' })).toHaveTextContent('Not enough in stock: Rice'), { timeout: 3000 })
  })

  it('shows a readable error when the backend is down, not a blank card', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('x')))
    render(<MemoryRouter><TestAuth user={null}><Landing /></TestAuth></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/Cannot reach the SWARA AI server/)).toBeInTheDocument(), { timeout: 3000 })
  })

  it('says plainly, without an error box, when the owner has switched the public demo off', async () => {
    renderIt(null, { 'POST /api/text/parse': () => err(403, 'DEMO_OFF', 'The live demo is switched off on this server. Sign in to use the order desk.') })
    expect(await screen.findByText(/live demo is switched off on this server/i, undefined, { timeout: 3000 })).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByLabelText(/type or paste what a customer would say/i)).toBeNull()
    const demo = screen.getByRole('region', { name: 'Live language demo' })
    expect(within(demo).getByRole('link', { name: 'Sign in' })).toHaveAttribute('href', '/sign-in')
  })

  it('example chips replace the text and trigger a new parse', async () => {
    const { calls } = renderIt()
    const parses = () => calls.filter((c) => c.url === '/api/text/parse')
    await waitFor(() => expect(parses()).toHaveLength(1), { timeout: 3000 })
    await userEvent.click(screen.getByRole('button', { name: 'ગુજરાતી' }))
    await waitFor(() => expect(parses()).toHaveLength(2), { timeout: 3000 })
    expect(JSON.parse(parses()[1].body!).text).toContain('કિલો')
  })
})

describe('Landing: contact form', () => {
  const form = () => within(screen.getByRole('form', { name: 'Contact form' }))
  const ROUTES = { ...PARSE, 'POST /api/contact': { ok: true, forwarded: false, message: 'Thanks. Your message was saved on this server for the shop owner to read.' } }

  it('checks every field before sending and puts focus on the first problem', async () => {
    const { calls } = renderIt(null, ROUTES)
    await userEvent.click(form().getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('Enter your name (2 to 80 characters).')).toBeInTheDocument()
    expect(form().getByLabelText('Your name')).toHaveFocus()
    await userEvent.type(form().getByLabelText('Your name'), 'Asha Shah')
    await userEvent.type(form().getByLabelText('E-mail address'), 'not-an-address')
    await userEvent.type(form().getByLabelText('Message'), 'short')
    await userEvent.click(form().getByRole('button', { name: 'Send message' }))
    expect(await screen.findByText('Enter a valid e-mail address so we can reply.')).toBeInTheDocument()
    expect(screen.getByText('Write at least 10 characters.')).toBeInTheDocument()
    expect(calls.some((c) => c.url === '/api/contact')).toBe(false)
  })

  it('sends the message, shows the server wording (saved, not "sent"), and clears the form', async () => {
    const { calls } = renderIt(null, ROUTES)
    await userEvent.type(form().getByLabelText('Your name'), '  Asha   Shah ')
    await userEvent.type(form().getByLabelText('E-mail address'), 'asha@example.com')
    await userEvent.selectOptions(form().getByLabelText('What is it about?'), 'demo')
    await userEvent.type(form().getByLabelText('Message'), 'Could I see how stock alerts work?')
    await userEvent.click(form().getByRole('button', { name: 'Send message' }))
    expect(await form().findByRole('status')).toHaveTextContent('Thanks. Your message was saved on this server for the shop owner to read.')
    expect(JSON.parse(calls.find((c) => c.url === '/api/contact')!.body!)).toEqual({
      name: 'Asha Shah', email: 'asha@example.com', topic: 'demo', message: 'Could I see how stock alerts work?', website: '' })
    expect((form().getByLabelText('Your name') as HTMLInputElement).value).toBe('')
    expect((form().getByLabelText('Message') as HTMLTextAreaElement).value).toBe('')
  })

  it('keeps a hidden trap field that people never reach by keyboard or screen reader', () => {
    renderIt(null, ROUTES)
    const trap = document.querySelector<HTMLInputElement>('input[name="website"]')!
    expect(trap.tabIndex).toBe(-1)
    expect(trap.closest('[aria-hidden="true"]')).not.toBeNull()
  })

  it('shows server problems next to the field they belong to, or as one clear message', async () => {
    mockRoutes({ ...PARSE, 'POST /api/contact': () => err(422, 'BAD_EMAIL', 'Enter a valid e-mail address so we can reply.') })
    const { unmount } = render(<MemoryRouter><TestAuth user={null}><Landing /></TestAuth></MemoryRouter>)
    const fill = async () => {
      await userEvent.type(form().getByLabelText('Your name'), 'Asha Shah')
      await userEvent.type(form().getByLabelText('E-mail address'), 'asha@example.co')
      await userEvent.type(form().getByLabelText('Message'), 'A message that is long enough.')
      await userEvent.click(form().getByRole('button', { name: 'Send message' }))
    }
    await fill()
    expect(await screen.findByText('Enter a valid e-mail address so we can reply.')).toBeInTheDocument()
    expect(form().getByLabelText('E-mail address')).toHaveFocus()
    unmount()
    mockRoutes({ ...PARSE, 'POST /api/contact': () => err(429, 'RATE_LIMITED', 'Too many requests. Wait a moment and try again.') })
    render(<MemoryRouter><TestAuth user={null}><Landing /></TestAuth></MemoryRouter>)
    await fill()
    expect(await screen.findByRole('alert')).toHaveTextContent('Too many requests')
  })

  it('is honest about what happens to a message', () => {
    renderIt(null, ROUTES)
    expect(screen.getByText(/saved on this server for the shop owner to read/)).toBeInTheDocument()
    expect(screen.getByText(/No reply time is promised/)).toBeInTheDocument()
  })
})

describe('Landing: security and trust', () => {
  it('has a Security and trust section listing what the code does, in the order of the content file', () => {
    renderIt()
    const sec = within(screen.getByRole('region', { name: 'Security and trust' }))
    expect(sec.getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual(SECURITY.map((x) => x.title))
    for (const item of SECURITY) expect(sec.getByText(item.body)).toBeInTheDocument()
  })

  it('states the limits right next to the claims: no audit, no certification, no two-factor', () => {
    renderIt()
    const sec = within(screen.getByRole('region', { name: 'Security and trust' }))
    expect(sec.getByText('What we do not claim.')).toBeInTheDocument()
    expect(sec.getByText(SECURITY_LIMITS, { exact: false })).toBeInTheDocument()
    expect(SECURITY_LIMITS).toMatch(/not had an independent security audit/)
    expect(SECURITY_LIMITS).toMatch(/no two-factor/)
  })

  it('never claims a certification, compliance standard, or encryption it does not provide', () => {
    const text = [...SECURITY.map((s) => `${s.title} ${s.body}`)].join(' ')
    expect(text).not.toMatch(/SOC ?2|ISO ?27001|GDPR|HIPAA|PCI|certified|military|bank-grade|unhackable|100%|end-to-end|AES|encrypted at rest/i)
  })

  it('is reachable from the footer as well as from the top bar', () => {
    renderIt()
    expect(within(screen.getByRole('contentinfo')).getByRole('link', { name: 'Security' })).toHaveAttribute('href', '#security')
  })
})

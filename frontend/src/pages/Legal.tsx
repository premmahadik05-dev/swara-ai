import { useEffect, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'

function Page({ title, updated, children }: { title: string; updated: string; children: ReactNode }) {
  useEffect(() => { document.title = `${title} · SWARA AI` }, [title])
  return (
    <div className="legal">
      <header className="legal-top"><Link to="/" aria-label="SWARA AI, home"><Logo height={34} decorative /></Link><Link to="/" className="btn secondary small">Back to home</Link></header>
      <main className="legal-body" id="main" tabIndex={-1}>
        <h1>{title}</h1>
        <p className="muted small">Last updated {updated}</p>
        <div className="note warn" role="note"><b>Template.</b> This text describes what the software does. It is a starting point, not legal advice. Whoever runs a public SWARA AI service should have it reviewed by a lawyer for their country and business before launch.</div>
        {children}
      </main>
    </div>
  )
}

export function Terms() {
  return (
    <Page title="Terms of Use" updated="10 November 2026">
      <h2>1. What SWARA AI is</h2>
      <p>SWARA AI is software that helps a shop take orders by voice or text, keep stock counts and see sales numbers. It runs on a server chosen by the shop owner.</p>
      <h2>2. Accounts</h2>
      <p>You need an account to use the app. Keep your password private; anything done while signed in with your account is treated as done by you. The shop owner can turn staff accounts on and off.</p>
      <h2>3. Acceptable use</h2>
      <p>Do not try to break into other accounts, overload the service, or use it to store or send unlawful material. The service limits repeated sign-in attempts to protect accounts.</p>
      <h2>4. Your shop's data</h2>
      <p>Products, prices, customers and orders you enter belong to your shop. Demo data that ships with the software is generated, is labelled as such, and does not describe real customers or sales.</p>
      <h2>5. Voice features</h2>
      <p>Voice ordering sends the recorded audio and text to Gnani AI for speech recognition and speech synthesis, using the API key the owner provides. Speech recognition can make mistakes: check the bill before confirming an order.</p>
      <h2>6. No warranty</h2>
      <p>The software is provided as it is, without warranties of any kind, to the extent the law allows. Check stock counts and totals against your own records.</p>
      <h2>7. Changes and contact</h2>
      <p>These terms may change; the date above shows the latest version. Questions can be sent through the contact form on the <Link to="/#contact">home page</Link>.</p>
    </Page>
  )
}

export function Privacy() {
  return (
    <Page title="Privacy Policy" updated="10 November 2026">
      <h2>What is stored about you</h2>
      <ul>
        <li><b>Account:</b> your name, e-mail address, a salted scrypt hash of your password (never the password), your role, when you accepted these terms and when you last signed in.</li>
        <li><b>Sessions:</b> for each signed-in browser, a hash of its session secret, the browser and system type, and when it was last active.</li>
        <li><b>Contact messages:</b> what you type into the contact form, kept for the shop owner.</li>
      </ul>
      <h2>What is stored about the shop</h2>
      <p>Products, stock, customers (name, phone and notes the shop enters), orders, and conversation transcripts from the Order desk. This stays in the database on the shop's own server.</p>
      <h2>Who else receives data</h2>
      <ul>
        <li><b>Gnani AI</b> receives the audio you record and the text it speaks back, only when voice ordering is used and the owner has set a Gnani key. See Gnani's own policy for how they handle it.</li>
        <li><b>A mail server</b> receives your e-mail address and the message, only if the owner has set up e-mail for confirmations and password resets.</li>
        <li>No advertising or analytics service receives anything from this app.</li>
      </ul>
      <h2>Cookies and browser storage</h2>
      <p>One cookie keeps you signed in. It is marked HttpOnly (scripts cannot read it) and is not used for tracking. The browser also remembers your sidebar and demo-data choices on your device.</p>
      <h2>Logs</h2>
      <p>The server writes sign-in events (account number, time, network address) to its log to help spot abuse. Passwords, session secrets and reset links are never written to it.</p>
      <h2>Your choices</h2>
      <p>You can change your name, password and language on the Account page and sign out of any device. To have an account removed, ask the shop owner, who runs the server and holds the data.</p>
    </Page>
  )
}

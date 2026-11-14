import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { Logo } from '../components/Logo'

export default function NotFound() {
  useEffect(() => { document.title = 'Page not found · SWARA AI' }, [])
  return (
    <main className="notfound" id="main" tabIndex={-1}>
      <Link to="/" aria-label="SWARA AI, home"><Logo height={38} decorative /></Link>
      <h1>This page does not exist</h1>
      <p className="muted">The address may be mistyped, or the page was moved.</p>
      <div className="row"><Link className="btn" to="/">Go to the home page</Link><Link className="btn secondary" to="/dashboard">Open the dashboard</Link></div>
    </main>
  )
}

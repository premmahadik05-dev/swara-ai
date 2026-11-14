import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { AuthLayout, FormAlert } from '../../components/AuthKit'
import { errMessage } from './helpers'

export default function VerifyEmail() {
  const [token] = useState(() => new URLSearchParams(window.location.search).get('token') ?? '')
  const [state, setState] = useState<'working' | 'ok' | 'bad'>(token ? 'working' : 'bad')
  const [msg, setMsg] = useState('The confirmation link is missing its code.')
  const started = useRef(false)   // the link works once; React's dev double-run must not spend it twice

  useEffect(() => {
    document.title = 'Confirm e-mail · SWARA AI'
    if (token) window.history.replaceState(null, '', window.location.pathname)
    if (!token || started.current) return
    started.current = true
    api.verifyEmail(token).then(() => setState('ok')).catch((e) => { setMsg(errMessage(e)); setState('bad') })
  }, [token])

  return (
    <AuthLayout title={state === 'ok' ? 'E-mail confirmed' : state === 'working' ? 'Confirming your e-mail…' : 'Could not confirm your e-mail'}>
      {state === 'working' && <div className="auth-done" role="status"><span className="spinner" aria-hidden /> One moment.</div>}
      {state === 'ok' && (
        <div className="auth-done" role="status">
          <p>Thank you. Your e-mail address is confirmed and you can sign in.</p>
          <div className="auth-actions"><Link className="btn large" to="/sign-in">Go to sign in</Link></div>
        </div>
      )}
      {state === 'bad' && (
        <>
          <FormAlert tone="bad">{msg}</FormAlert>
          <p className="muted">Sign in with your e-mail and password; if the address is still unconfirmed you can ask for a new link there. <Link to="/sign-in">Go to sign in</Link></p>
        </>
      )}
    </AuthLayout>
  )
}

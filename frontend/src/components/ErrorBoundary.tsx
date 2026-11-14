import { Component, type ErrorInfo, type ReactNode } from 'react'
import { Button, Empty } from './ui'

/** Catches a crash inside one screen so the sidebar and the rest of the app keep working. */
export class ErrorBoundary extends Component<{ children: ReactNode; resetKey?: string }, { error: Error | null }> {
  state = { error: null as Error | null }
  static getDerivedStateFromError(error: Error) { return { error } }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('Screen crashed:', error, info.componentStack) }
  componentDidUpdate(prev: { resetKey?: string }) { if (this.state.error && prev.resetKey !== this.props.resetKey) this.setState({ error: null }) }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="card" role="alert" style={{ margin: '40px auto', maxWidth: 560 }}>
        <Empty title="This screen hit a problem" icon="alert"
               action={<><Button onClick={() => this.setState({ error: null })}>Try again</Button><Button variant="secondary" onClick={() => location.assign('/dashboard')}>Go to dashboard</Button></>}>
          {this.state.error.message || 'Unexpected error'}. Your data is safe; nothing was changed by this error.
        </Empty>
      </div>
    )
  }
}

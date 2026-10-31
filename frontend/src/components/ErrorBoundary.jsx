import { Component } from 'react'

// Last-resort guard so a rendering or import failure shows a readable message
// instead of a blank page. The phone route in particular must never silently
// render nothing, because a failed API request or bad token would otherwise
// look like a white screen.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    // Keep the diagnostic in the console for debugging; never swallow it.
    console.error('Namma Space render error:', error, info?.componentStack)
  }

  render() {
    if (this.state.error) {
      return (
        <div
          role="alert"
          className="min-h-screen flex flex-col items-center justify-center gap-3 bg-neutral-950 p-6 text-center text-neutral-100"
        >
          <h1 className="text-lg font-semibold">Something went wrong</h1>
          <p className="max-w-md text-sm text-neutral-400">
            The page could not render. Reload and try again; if the problem
            persists, check the browser console for details.
          </p>
          <pre className="max-w-md overflow-auto rounded-lg border border-white/10 bg-black/40 p-3 text-left text-xs text-red-300">
            {String(this.state.error?.message || this.state.error)}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-lg bg-fuchsia-600 px-4 py-2 text-sm font-semibold text-white hover:bg-fuchsia-500"
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

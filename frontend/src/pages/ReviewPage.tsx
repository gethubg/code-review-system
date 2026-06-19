import { useState, useId, FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { GitBranch, ArrowRight, Loader2, Shield, Zap, FileCode, Star } from 'lucide-react'
import { api } from '../lib/api.ts'
import { ProgressFeed } from '../components/ProgressFeed.tsx'
import { useProgressFeed } from '../lib/ws.ts'

function isValidGitUrl(url: string): boolean {
  try {
    const parsed = new URL(url)
    return ['http:', 'https:', 'git:'].includes(parsed.protocol)
  } catch {
    return false
  }
}

const FEATURE_CARDS = [
  {
    icon: <Shield size={20} style={{ color: 'var(--color-critical)' }} aria-hidden="true" />,
    title: 'Security Agent',
    desc: 'Detects OWASP Top-10 vulnerabilities, injection flaws, and secrets leakage across the full codebase.',
  },
  {
    icon: <Zap size={20} style={{ color: 'var(--color-high)' }} aria-hidden="true" />,
    title: 'Bug Agent',
    desc: 'Spots logic errors, null-dereferences, off-by-one mistakes, and common anti-patterns.',
  },
  {
    icon: <FileCode size={20} style={{ color: 'var(--color-accent)' }} aria-hidden="true" />,
    title: 'Coverage Agent',
    desc: 'Evaluates test depth, flags untested critical paths, and estimates overall coverage score.',
  },
  {
    icon: <Star size={20} style={{ color: 'var(--color-completed)' }} aria-hidden="true" />,
    title: 'Production Score',
    desc: 'Aggregates findings into a single actionable readiness score with a clear pass/fail verdict.',
  },
]

export function ReviewPage() {
  const navigate = useNavigate()
  const inputId = useId()
  const errorId = useId()

  const [gitUrl, setGitUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)

  const { messages, isConnected } = useProgressFeed(activeRunId)

  // Navigate to results once the complete event arrives
  const isDone = messages.some(m => m.type === 'complete' || m.type === 'error')
  if (activeRunId && isDone) {
    // Give user a moment to read the final message
    setTimeout(() => navigate(`/results/${activeRunId}`), 800)
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)

    const trimmed = gitUrl.trim()
    if (!trimmed) {
      setError('Please enter a Git repository URL.')
      return
    }
    if (!isValidGitUrl(trimmed)) {
      setError('Please enter a valid URL — e.g. https://github.com/org/repo')
      return
    }

    setLoading(true)
    try {
      const { data } = await api.submitReview(trimmed)
      setActiveRunId(data.run_id)
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : 'Failed to submit review. Check the URL and try again.'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="review-page">
      {/* Hero */}
      <section className="review-page__hero" aria-labelledby="review-heading">
        <div className="review-page__icon" aria-hidden="true">
          <GitBranch size={40} />
        </div>
        <h1 id="review-heading" className="review-page__heading">
          AI Code Review
        </h1>
        <p className="review-page__sub">
          Paste any public Git repository URL. Our multi-agent system analyses
          security, bugs, and test coverage — delivering a production-readiness
          verdict in seconds.
        </p>
      </section>

      {/* Form */}
      <form
        className="review-form"
        onSubmit={handleSubmit}
        aria-label="Submit repository for review"
        noValidate
      >
        <label htmlFor={inputId} className="review-form__label">
          Git Repository URL
        </label>
        <div className="review-form__row">
          <input
            id={inputId}
            type="url"
            className="review-form__input"
            placeholder="https://github.com/org/repo"
            value={gitUrl}
            onChange={e => {
              setGitUrl(e.target.value)
              if (error) setError(null)
            }}
            disabled={loading || activeRunId !== null}
            autoComplete="url"
            spellCheck={false}
            aria-describedby={error ? errorId : undefined}
            aria-invalid={error ? 'true' : undefined}
          />
          <button
            type="submit"
            className="btn btn--primary"
            disabled={loading || !gitUrl.trim() || activeRunId !== null}
            style={{ minWidth: 148, padding: '0.75rem 1.25rem', fontSize: '1rem' }}
          >
            {loading ? (
              <>
                <Loader2 size={16} className="spin" aria-hidden="true" />
                Submitting…
              </>
            ) : (
              <>
                Start Review
                <ArrowRight size={16} aria-hidden="true" />
              </>
            )}
          </button>
        </div>

        {error && (
          <p id={errorId} className="review-form__error" role="alert">
            {error}
          </p>
        )}
      </form>

      {/* Live progress feed — visible after submission */}
      {activeRunId && (
        <section aria-label="Review progress">
          <ProgressFeed messages={messages} isConnected={isConnected} />
        </section>
      )}

      {/* Feature highlights — hidden once a run is active to reduce visual noise */}
      {!activeRunId && (
        <section className="review-page__features" aria-label="Feature highlights">
          {FEATURE_CARDS.map(card => (
            <article key={card.title} className="feature-card">
              {card.icon}
              <h2 className="feature-card__title">{card.title}</h2>
              <p className="feature-card__desc">{card.desc}</p>
            </article>
          ))}
        </section>
      )}
    </main>
  )
}

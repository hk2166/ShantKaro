import { useEffect, useState } from 'react'

import { type CallState, fetchReport, type Line, type Report, type Scenario } from '../api.ts'
import { Avatar, Spinner } from '../components.tsx'
import { isCalming, outcome, tagLabel } from '../labels.ts'

const SCORE_NAMES: Record<string, string> = {
  empathy: 'Empathy',
  resolution: 'Resolution',
  policy_compliance: 'Policy',
  language_adaptation: 'Language',
  efficiency: 'Efficiency',
}

const SCORE_HELP: Record<string, string> = {
  empathy: 'Acknowledged feelings, apologised, used their name',
  resolution: 'Offered a fix the policy allows',
  policy_compliance: "Didn't promise anything forbidden",
  language_adaptation: 'Followed the customer into their language',
  efficiency: 'Calmed them quickly, without rambling',
}

export function ReportView({
  scenario,
  sessionId,
  finalState,
  onRetry,
  onPickAnother,
}: {
  scenario: Scenario
  sessionId: string
  finalState: CallState | null
  onRetry: () => void
  onPickAnother: () => void
}) {
  const [report, setReport] = useState<Report | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const abort = new AbortController()
    fetchReport(sessionId, abort.signal)
      .then(setReport)
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => abort.abort()
  }, [sessionId])

  const status = report?.status ?? finalState?.status ?? 'ended_by_trainee'
  const { title, detail } = outcome(status, finalState?.last_tags)

  return (
    <main className="page narrow">
      <section className={`card result result-${status}`}>
        <Avatar scenario={scenario} size={56} />
        <div>
          <p className="eyebrow">Call with {scenario.persona.name}</p>
          <h1>{title}</h1>
          <p className="muted">{detail}</p>
        </div>
        {report?.total != null && (
          <div className="total" aria-label={`Total score ${report.total} out of 100`}>
            {report.total}
            <small>/100</small>
          </div>
        )}
      </section>

      {!report && !error && <Spinner label="Scoring your call and writing your coaching tips…" />}
      {error && (
        <div className="notice error" role="alert">
          <strong>No report card this time</strong>
          <p>{error}</p>
        </div>
      )}

      {report && report.turns === 0 && (
        <div className="notice" role="status">
          <strong>Nothing to score yet</strong>
          <p>The call ended before you said anything. Give it another go!</p>
        </div>
      )}

      {report?.scores && (
        <section className="card">
          <h2>Report card</h2>
          <ul className="scores">
            {Object.entries(report.scores).map(([name, value]) => (
              <li key={name}>
                <div className="score-row">
                  <span>{SCORE_NAMES[name] ?? name}</span>
                  <span className="score-value">{value === null ? 'Not tested' : value}</span>
                </div>
                <div className="score-track">
                  <div className="score-fill" style={{ width: `${value ?? 0}%` }} />
                </div>
                <p className="muted small">{SCORE_HELP[name]}</p>
              </li>
            ))}
          </ul>
        </section>
      )}

      {report && (report.best_line || report.worst_line) && (
        <section className="lines">
          {report.best_line && <LineCard title="Your best line" line={report.best_line} good />}
          {report.worst_line && <LineCard title="Your worst line" line={report.worst_line} />}
        </section>
      )}

      {report && report.tips.length > 0 && (
        <section className="card">
          <h2>Coaching tips</h2>
          <ol className="tips">
            {report.tips.map((tip) => (
              <li key={tip.advice}>
                {tip.quote && <blockquote>“{tip.quote}”</blockquote>}
                <p>{tip.advice}</p>
                <p className="try">
                  <strong>Try saying:</strong> {tip.try_saying}
                </p>
              </li>
            ))}
          </ol>
        </section>
      )}

      <div className="actions">
        <button type="button" className="primary" onClick={onRetry}>
          Call {scenario.persona.name} again
        </button>
        <button type="button" className="ghost" onClick={onPickAnother}>
          Pick another customer
        </button>
      </div>
    </main>
  )
}

function LineCard({ title, line, good = false }: { title: string; line: Line; good?: boolean }) {
  const change = line.anger_after - line.anger_before
  return (
    <div className={`card line ${good ? 'good' : 'bad'}`}>
      <h3>{title}</h3>
      <blockquote>“{line.line}”</blockquote>
      <p className="tags">
        {line.tags.map((tag) => (
          <span key={tag} className={`tag ${isCalming(tag) ? 'good' : 'bad'}`}>
            {tagLabel(tag)}
          </span>
        ))}
        <span className={`delta ${change < 0 ? 'good' : change > 0 ? 'bad' : ''}`}>
          anger {line.anger_before} → {line.anger_after}
        </span>
      </p>
    </div>
  )
}

import { MessageSquareOff, RotateCw } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'

import { type CallState, fetchReport, type Line, type Report, type Scenario } from '../api.ts'
import { Avatar } from '../components.tsx'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '../components/reui/alert.tsx'
import { Badge } from '../components/reui/badge.tsx'
import { Button } from '../components/ui/button.tsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card.tsx'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '../components/ui/empty.tsx'
import { Progress, ProgressLabel, ProgressValue } from '../components/ui/progress.tsx'
import { Skeleton } from '../components/ui/skeleton.tsx'
import { isCalming, outcome, tagLabel } from '../labels.ts'

const SCORES: { key: keyof NonNullable<Report['scores']>; name: string; help: string }[] = [
  { key: 'empathy', name: 'Empathy', help: 'Acknowledged feelings, apologised, used their name' },
  { key: 'resolution', name: 'Resolution', help: 'Offered a fix the policy allows' },
  { key: 'policy_compliance', name: 'Policy', help: "Didn't promise anything forbidden" },
  { key: 'language_adaptation', name: 'Language', help: 'Followed the customer into their language' },
  { key: 'efficiency', name: 'Efficiency', help: 'Calmed them quickly, without rambling' },
]

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
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const abort = new AbortController()
    fetchReport(sessionId, abort.signal)
      .then(setReport)
      .catch((reason: unknown) => {
        if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : String(reason))
      })
    return () => abort.abort()
  }, [sessionId, attempt])

  const reload = useCallback(() => {
    setError('')
    setAttempt((count) => count + 1)
  }, [])

  const status = report?.status ?? finalState?.status ?? 'ended_by_trainee'
  const { title, detail } = outcome(status, finalState?.last_tags)
  const loading = !report && !error

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-4">
            <Avatar scenario={scenario} large />
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <CardDescription>Call with {scenario.persona.name}</CardDescription>
              <CardTitle>{title}</CardTitle>
              <p className="text-sm text-muted-foreground">{detail}</p>
            </div>
            {report?.total != null && (
              <div className="flex flex-col items-end gap-0.5">
                <span className="text-2xl font-semibold tracking-tight tabular-nums">{report.total}</span>
                <span className="text-xs text-muted-foreground">out of 100</span>
              </div>
            )}
          </div>
        </CardHeader>
      </Card>

      {error && (
        <Alert variant="destructive">
          <AlertTitle>No report card yet</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
          <AlertAction>
            <Button variant="outline" size="sm" onClick={reload}>
              <RotateCw data-icon="inline-start" />
              Retry
            </Button>
          </AlertAction>
        </Alert>
      )}

      {loading && <ReportSkeleton />}

      {report && report.turns === 0 && (
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon">
              <MessageSquareOff />
            </EmptyMedia>
            <EmptyTitle>Nothing to score yet</EmptyTitle>
            <EmptyDescription>The call ended before you said anything.</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <Button onClick={onRetry}>Call {scenario.persona.name} again</Button>
          </EmptyContent>
        </Empty>
      )}

      {report?.scores && (
        <Card>
          <CardHeader>
            <CardTitle>Report card</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-col gap-4">
            {SCORES.map(({ key, name, help }) => {
              const value = report.scores?.[key] ?? null
              return (
                <div key={key} className="flex flex-col gap-1">
                  <Progress value={value ?? 0}>
                    <ProgressLabel>{name}</ProgressLabel>
                    <ProgressValue>{() => (value === null ? 'Not tested' : value)}</ProgressValue>
                  </Progress>
                  <p className="text-xs text-muted-foreground">{help}</p>
                </div>
              )
            })}
          </CardContent>
        </Card>
      )}

      {report && (report.best_line || report.worst_line) && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          {report.best_line && <LineCard title="Your best line" line={report.best_line} />}
          {report.worst_line && <LineCard title="Your worst line" line={report.worst_line} />}
        </div>
      )}

      {report && report.tips.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Coaching tips</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-col gap-4">
              {report.tips.map((tip) => (
                <li key={tip.advice} className="flex flex-col gap-1 text-sm">
                  {tip.quote && <p className="text-muted-foreground italic">“{tip.quote}”</p>}
                  <p>{tip.advice}</p>
                  <p>
                    <span className="font-medium">Try saying:</span> {tip.try_saying}
                  </p>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {report && report.turns > 0 && (
        <div className="flex flex-wrap gap-2">
          <Button onClick={onRetry}>Call {scenario.persona.name} again</Button>
          <Button variant="outline" onClick={onPickAnother}>
            Pick another customer
          </Button>
        </div>
      )}
      {(!report || report.turns === 0) && (
        <div>
          <Button variant="outline" onClick={onPickAnother}>
            Pick another customer
          </Button>
        </div>
      )}
    </main>
  )
}

function LineCard({ title, line }: { title: string; line: Line }) {
  const change = line.anger_after - line.anger_before
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm italic">“{line.line}”</p>
        <div className="flex flex-wrap gap-1">
          {line.tags.map((tag) => (
            <Badge key={tag} variant={isCalming(tag) ? 'success-light' : 'destructive-light'}>
              {tagLabel(tag)}
            </Badge>
          ))}
          <Badge variant={change < 0 ? 'success-light' : change > 0 ? 'destructive-light' : 'outline'}>
            Anger {line.anger_before} → {line.anger_after}
          </Badge>
        </div>
      </CardContent>
    </Card>
  )
}

function ReportSkeleton() {
  return (
    <Card role="status" aria-label="Scoring your call and writing your coaching tips">
      <CardHeader>
        <Skeleton className="h-4 w-28" />
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {SCORES.map(({ key }) => (
          <div key={key} className="flex flex-col gap-2">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-1 w-full" />
          </div>
        ))}
        <p className="text-xs text-muted-foreground">Your coach is writing tips…</p>
      </CardContent>
    </Card>
  )
}

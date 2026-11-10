import { lazy, Suspense, useCallback, useEffect, useState } from 'react'

import {
  type CallState,
  fetchScenarios,
  type Scenario,
  StartRefused,
  startSession,
} from './api.ts'
import { Alert, AlertDescription, AlertTitle } from './components/reui/alert.tsx'
import { Button } from './components/ui/button.tsx'
import { Brief } from './screens/Brief.tsx'
import { Picker } from './screens/Picker.tsx'
import { ReportView } from './screens/ReportView.tsx'

// The voice SDK is most of the app's size, so it loads only when a call starts.
const Call = lazy(() => import('./screens/Call.tsx').then((module) => ({ default: module.Call })))

type Screen =
  | { name: 'picker' }
  | { name: 'brief'; scenario: Scenario }
  | { name: 'call'; scenario: Scenario; sessionId: string }
  | { name: 'report'; scenario: Scenario; sessionId: string; finalState: CallState | null }
  | { name: 'refused'; scenario: Scenario; message: string }

export default function App() {
  const [scenarios, setScenarios] = useState<Scenario[] | null>(null)
  const [loadError, setLoadError] = useState('')
  const [loadAttempt, setLoadAttempt] = useState(0)
  const [screen, setScreen] = useState<Screen>({ name: 'picker' })
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    fetchScenarios()
      .then(setScenarios)
      .catch((reason: unknown) => setLoadError(reason instanceof Error ? reason.message : String(reason)))
  }, [loadAttempt])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [screen.name])

  const retryLoad = useCallback(() => {
    setLoadError('')
    setScenarios(null)
    setLoadAttempt((count) => count + 1)
  }, [])

  async function startCall(scenario: Scenario) {
    setStarting(true)
    try {
      const sessionId = await startSession(scenario.id)
      setScreen({ name: 'call', scenario, sessionId })
    } catch (reason) {
      const message =
        reason instanceof StartRefused
          ? reason.message
          : "We couldn't reach the server. Check your connection and try again."
      setScreen({ name: 'refused', scenario, message })
    } finally {
      setStarting(false)
    }
  }

  const callEnded = useCallback(
    (scenario: Scenario, sessionId: string) => (finalState: CallState | null) =>
      setScreen({ name: 'report', scenario, sessionId, finalState }),
    [],
  )

  switch (screen.name) {
    case 'picker':
      return (
        <Picker
          scenarios={scenarios}
          error={loadError}
          onRetry={retryLoad}
          onPick={(scenario) => setScreen({ name: 'brief', scenario })}
        />
      )
    case 'brief':
      return (
        <Brief
          scenario={screen.scenario}
          starting={starting}
          onStart={() => startCall(screen.scenario)}
          onBack={() => setScreen({ name: 'picker' })}
        />
      )
    case 'call':
      return (
        <Suspense
          fallback={
            <main className="mx-auto w-full max-w-2xl px-4 py-8 text-sm text-muted-foreground" role="status">
              Connecting the call…
            </main>
          }
        >
          <Call
            key={screen.sessionId}
            scenario={screen.scenario}
            sessionId={screen.sessionId}
            onEnded={callEnded(screen.scenario, screen.sessionId)}
          />
        </Suspense>
      )
    case 'report':
      return (
        <ReportView
          scenario={screen.scenario}
          sessionId={screen.sessionId}
          finalState={screen.finalState}
          onRetry={() => setScreen({ name: 'brief', scenario: screen.scenario })}
          onPickAnother={() => setScreen({ name: 'picker' })}
        />
      )
    case 'refused':
      return (
        <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
          <Alert variant="warning">
            <AlertTitle>We couldn't connect you</AlertTitle>
            <AlertDescription>{screen.message}</AlertDescription>
          </Alert>
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => setScreen({ name: 'brief', scenario: screen.scenario })}>Try again</Button>
            <Button variant="outline" onClick={() => setScreen({ name: 'picker' })}>
              Pick another customer
            </Button>
          </div>
        </main>
      )
  }
}

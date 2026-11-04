import { lazy, Suspense, useCallback, useEffect, useState } from 'react'

import {
  type CallState,
  fetchScenarios,
  type Scenario,
  StartRefused,
  startSession,
} from './api.ts'
import { Spinner } from './components.tsx'
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
  const [screen, setScreen] = useState<Screen>({ name: 'picker' })
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    fetchScenarios()
      .then(setScenarios)
      .catch((reason: unknown) => setLoadError(reason instanceof Error ? reason.message : String(reason)))
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0 })
  }, [screen.name])

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

  if (loadError) {
    return (
      <main className="page narrow">
        <div className="notice error" role="alert">
          <strong>The training centre is closed right now</strong>
          <p>{loadError}. Please try again in a few minutes.</p>
        </div>
      </main>
    )
  }
  if (!scenarios) {
    return (
      <main className="page narrow">
        <Spinner label="Loading the customers…" />
      </main>
    )
  }

  switch (screen.name) {
    case 'picker':
      return <Picker scenarios={scenarios} onPick={(scenario) => setScreen({ name: 'brief', scenario })} />
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
            <main className="page narrow">
              <Spinner label="Connecting the call…" />
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
        <main className="page narrow">
          <div className="notice warn" role="alert">
            <strong>We couldn't connect you</strong>
            <p>{screen.message}</p>
          </div>
          <div className="actions">
            <button type="button" className="primary" onClick={() => setScreen({ name: 'brief', scenario: screen.scenario })}>
              Try again
            </button>
            <button type="button" className="ghost" onClick={() => setScreen({ name: 'picker' })}>
              Pick another customer
            </button>
          </div>
        </main>
      )
  }
}

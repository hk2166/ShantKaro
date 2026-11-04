import { useState } from 'react'

import type { Scenario } from '../api.ts'
import { AngerMeter, Avatar, Spinner } from '../components.tsx'
import { languageName } from '../labels.ts'

type MicProblem = 'denied' | 'missing' | 'unsupported' | null

/** Ask for the microphone before the call, so the permission prompt doesn't eat call time. */
async function askForMic(): Promise<MicProblem> {
  if (!navigator.mediaDevices?.getUserMedia) return 'unsupported'
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    stream.getTracks().forEach((track) => track.stop())
    return null
  } catch (error) {
    const name = error instanceof DOMException ? error.name : ''
    return name === 'NotFoundError' || name === 'OverconstrainedError' ? 'missing' : 'denied'
  }
}

const MIC_HELP: Record<Exclude<MicProblem, null>, { title: string; detail: string }> = {
  denied: {
    title: 'Microphone blocked',
    detail:
      "The call needs your microphone. Click the lock or camera icon in your browser's address bar, allow the microphone for this site, then try again.",
  },
  missing: {
    title: 'No microphone found',
    detail: 'Plug in a headset or turn on your microphone, then try again.',
  },
  unsupported: {
    title: "This browser can't use a microphone here",
    detail: 'Open the site over https in a recent Chrome, Safari or Firefox.',
  },
}

export function Brief({
  scenario,
  starting,
  onStart,
  onBack,
}: {
  scenario: Scenario
  starting: boolean
  onStart: () => void
  onBack: () => void
}) {
  const [checkingMic, setCheckingMic] = useState(false)
  const [micProblem, setMicProblem] = useState<MicProblem>(null)

  async function start() {
    setCheckingMic(true)
    const problem = await askForMic()
    setCheckingMic(false)
    setMicProblem(problem)
    if (!problem) onStart()
  }

  const busy = checkingMic || starting
  return (
    <main className="page narrow">
      <button type="button" className="link-button" onClick={onBack} disabled={busy}>
        ← All customers
      </button>

      <section className="card brief-head">
        <Avatar scenario={scenario} size={72} />
        <div>
          <p className="eyebrow">
            {scenario.company} · {scenario.title}
          </p>
          <h1>{scenario.persona.name}</h1>
          <p className="lede">{scenario.summary}</p>
        </div>
      </section>

      <AngerMeter anger={scenario.starting_anger} />

      <section className="policy">
        <div className="card policy-col allowed">
          <h2>You may offer</h2>
          <ul>
            {scenario.allowed_remedies.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div className="card policy-col forbidden">
          <h2>You must not</h2>
          <ul>
            {scenario.forbidden_promises.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
          <p className="muted small">
            {scenario.max_strikes} broken rules and the customer hangs up.
          </p>
        </div>
      </section>

      <ul className="rules muted">
        <li>
          <strong>Win:</strong> anger down to 20 or below, with a fix the customer accepts.
        </li>
        <li>
          <strong>Time:</strong> {Math.round(scenario.time_limit_s / 60)} minutes. Insults end
          the call at once.
        </li>
        <li>
          <strong>Speak</strong> {scenario.languages.map(languageName).join(' or ')}. You can
          interrupt the customer, like on a real call.
        </li>
      </ul>

      {micProblem && (
        <div className="notice error" role="alert">
          <strong>{MIC_HELP[micProblem].title}</strong>
          <p>{MIC_HELP[micProblem].detail}</p>
        </div>
      )}

      <div className="actions">
        <button type="button" className="primary big" onClick={start} disabled={busy}>
          {busy ? <Spinner label="Connecting…" /> : micProblem ? 'Try again' : 'Start the call'}
        </button>
      </div>
    </main>
  )
}

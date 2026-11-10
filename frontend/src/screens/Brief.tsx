import { ArrowLeft, Check, MicOff, Phone, X } from 'lucide-react'
import { useState } from 'react'

import type { Scenario } from '../api.ts'
import { AngerMeter, Avatar } from '../components.tsx'
import { Alert, AlertDescription, AlertTitle } from '../components/reui/alert.tsx'
import { Button } from '../components/ui/button.tsx'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card.tsx'
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
      "Allow the microphone for this site from the icon in your browser's address bar, then try again.",
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
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
      <div>
        <Button variant="ghost" onClick={onBack} disabled={busy}>
          <ArrowLeft data-icon="inline-start" />
          All customers
        </Button>
      </div>

      <Card>
        <CardHeader>
          <div className="flex items-start gap-4">
            <Avatar scenario={scenario} large />
            <div className="flex min-w-0 flex-col gap-0.5">
              <CardDescription>
                {scenario.company}: {scenario.title}
              </CardDescription>
              <CardTitle>{scenario.persona.name}</CardTitle>
              <p className="text-sm text-muted-foreground">{scenario.summary}</p>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <AngerMeter anger={scenario.starting_anger} />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <PolicyCard title="You may offer" items={scenario.allowed_remedies} allowed />
        <PolicyCard
          title="You must not"
          description={`${scenario.max_strikes} broken rules and they hang up`}
          items={scenario.forbidden_promises}
        />
      </div>

      <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
        <li>
          <span className="font-medium text-foreground">Win:</span> anger down to 20 or below, with
          a fix the customer accepts.
        </li>
        <li>
          <span className="font-medium text-foreground">Time:</span>{' '}
          {Math.round(scenario.time_limit_s / 60)} minutes. Insults end the call at once.
        </li>
        <li>
          <span className="font-medium text-foreground">Speak</span>{' '}
          {scenario.languages.map(languageName).join(' or ')}. You can interrupt, like on a real
          call.
        </li>
      </ul>

      {micProblem && (
        <Alert variant="destructive">
          <MicOff />
          <AlertTitle>{MIC_HELP[micProblem].title}</AlertTitle>
          <AlertDescription>{MIC_HELP[micProblem].detail}</AlertDescription>
        </Alert>
      )}

      <Button size="lg" className="w-full" onClick={start} disabled={busy}>
        <Phone data-icon="inline-start" />
        {busy ? 'Connecting…' : micProblem ? 'Try again' : 'Start the call'}
      </Button>
    </main>
  )
}

function PolicyCard({
  title,
  description,
  items,
  allowed = false,
}: {
  title: string
  description?: string
  items: string[]
  allowed?: boolean
}) {
  const Icon = allowed ? Check : X
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ul className="flex flex-col gap-2 text-sm">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <Icon
                aria-hidden="true"
                className={
                  allowed
                    ? 'mt-0.5 size-4 shrink-0 text-success-foreground dark:text-success'
                    : 'mt-0.5 size-4 shrink-0 text-destructive-foreground dark:text-destructive'
                }
              />
              <span>{item}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  )
}

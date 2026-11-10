import {
  type BotTTSTextData,
  PipecatClient,
  RTVIEvent,
  type TranscriptData,
} from '@pipecat-ai/client-js'
import {
  PipecatClientAudio,
  PipecatClientProvider,
  useRTVIClientEvent,
} from '@pipecat-ai/client-react'
import { SmallWebRTCTransport } from '@pipecat-ai/small-webrtc-transport'
import { useCallback, useEffect, useRef, useState } from 'react'

import { Captions, PhoneOff } from 'lucide-react'

import { type CallState, offerEndpoint, type Scenario } from '../api.ts'
import { AngerMeter, Avatar } from '../components.tsx'
import { Alert, AlertDescription, AlertTitle } from '../components/reui/alert.tsx'
import { Badge } from '../components/reui/badge.tsx'
import { Button } from '../components/ui/button.tsx'
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card.tsx'
import { cn } from '@/lib/utils'
import { clock, isCalming, LANGUAGES, outcome, tagLabel } from '../labels.ts'

type Caption = { id: number; who: 'customer' | 'you'; text: string }
type Phase = 'connecting' | 'live' | 'ending' | 'failed'

// If the server ends the call but the connection doesn't close, stop waiting after this long.
const ENDING_TIMEOUT_MS = 20_000

export function Call(props: {
  scenario: Scenario
  sessionId: string
  onEnded: (finalState: CallState | null) => void
}) {
  // One client per call. React may run this twice in development; the extra one is never used.
  const [client] = useState(
    () =>
      new PipecatClient({
        transport: new SmallWebRTCTransport(),
        enableMic: true,
        enableCam: false,
      }),
  )
  return (
    <PipecatClientProvider client={client}>
      <CallRoom client={client} {...props} />
      <PipecatClientAudio />
    </PipecatClientProvider>
  )
}

function CallRoom({
  client,
  scenario,
  sessionId,
  onEnded,
}: {
  client: PipecatClient
  scenario: Scenario
  sessionId: string
  onEnded: (finalState: CallState | null) => void
}) {
  const [phase, setPhase] = useState<Phase>('connecting')
  const [error, setError] = useState('')
  const [state, setState] = useState<CallState | null>(null)
  const [previousAnger, setPreviousAnger] = useState<number | null>(null)
  const [turn, setTurn] = useState(0)
  const [captions, setCaptions] = useState<Caption[]>([])
  const [showCaptions, setShowCaptions] = useState(true)
  const [language, setLanguage] = useState(scenario.languages[0])
  const [customerSpeaking, setCustomerSpeaking] = useState(false)
  const [youSpeaking, setYouSpeaking] = useState(false)
  const [clockBase, setClockBase] = useState<{ elapsed: number; at: number } | null>(null)
  // The clock is read only in effects and event handlers (Date.now below), never in render.
  const [now, setNow] = useState(0)

  const finalState = useRef<CallState | null>(null)
  const finished = useRef(false)
  const started = useRef(false)
  const nextCaption = useRef(0)
  const captionsEnd = useRef<HTMLDivElement>(null)

  const finish = useCallback(() => {
    if (finished.current) return
    finished.current = true
    onEnded(finalState.current)
  }, [onEnded])

  // Connect once. Side effects stay out of cleanup, so React's development double-run of
  // effects can't hang up the call and start a second one for the same session.
  useEffect(() => {
    if (started.current) return
    started.current = true
    client
      .connect({ webrtcRequestParams: { endpoint: offerEndpoint(sessionId) } })
      .catch((reason: unknown) => {
        setPhase('failed')
        setError(reason instanceof Error ? reason.message : String(reason))
      })
  }, [client, sessionId])

  // Closing the tab mid-call should still hang up, so the server frees the line at once.
  useEffect(() => {
    const hangUpOnLeave = () => void client.disconnect()
    window.addEventListener('pagehide', hangUpOnLeave)
    return () => window.removeEventListener('pagehide', hangUpOnLeave)
  }, [client])

  useEffect(() => {
    if (phase !== 'live' && phase !== 'ending') return
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [phase])

  useEffect(() => {
    if (phase !== 'ending') return
    const timer = setTimeout(() => {
      void client.disconnect().finally(finish)
    }, ENDING_TIMEOUT_MS)
    return () => clearTimeout(timer)
  }, [phase, client, finish])

  useEffect(() => {
    captionsEnd.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [captions])

  const addCaption = useCallback((who: Caption['who'], text: string) => {
    const clean = text.trim()
    if (!clean) return
    setCaptions((current) => {
      const last = current.at(-1)
      // The customer's reply arrives one sentence at a time; keep it in one bubble.
      if (last && last.who === who && who === 'customer') {
        return [...current.slice(0, -1), { ...last, text: `${last.text} ${clean}` }]
      }
      nextCaption.current += 1
      return [...current, { id: nextCaption.current, who, text: clean }]
    })
  }, [])

  useRTVIClientEvent(RTVIEvent.BotReady, () => setPhase((p) => (p === 'connecting' ? 'live' : p)))

  useRTVIClientEvent(RTVIEvent.ServerMessage, (data: unknown) => {
    const message = data as Partial<CallState> | null
    if (message?.type !== 'call_state') return
    const update = message as CallState
    setState((current) => {
      setPreviousAnger(current ? current.anger : null)
      return update
    })
    if (update.last_tags.length > 0) setTurn((count) => count + 1)
    const at = Date.now()
    setClockBase({ elapsed: update.elapsed_s, at })
    setNow(at)
    setPhase((p) => (p === 'connecting' ? 'live' : p))
    if (update.status !== 'in_progress') {
      finalState.current = update
      setPhase('ending')
    }
  })

  useRTVIClientEvent(RTVIEvent.UserTranscript, (data: TranscriptData) => {
    if (data.final) addCaption('you', data.text)
  })
  useRTVIClientEvent(RTVIEvent.BotTtsText, (data: BotTTSTextData) => addCaption('customer', data.text))
  useRTVIClientEvent(RTVIEvent.BotStartedSpeaking, () => setCustomerSpeaking(true))
  useRTVIClientEvent(RTVIEvent.BotStoppedSpeaking, () => setCustomerSpeaking(false))
  useRTVIClientEvent(RTVIEvent.UserStartedSpeaking, () => setYouSpeaking(true))
  useRTVIClientEvent(RTVIEvent.UserStoppedSpeaking, () => setYouSpeaking(false))
  useRTVIClientEvent(RTVIEvent.Disconnected, () => {
    if (phase !== 'failed') finish()
  })

  async function hangUp() {
    setPhase('ending')
    await client.disconnect()
    finish()
  }

  function switchLanguage(code: string) {
    setLanguage(code)
    client.sendClientMessage('set_language', { language: code })
  }

  const limit = state?.time_limit_s ?? scenario.time_limit_s
  const elapsed = clockBase ? clockBase.elapsed + (now - clockBase.at) / 1000 : 0
  const remaining = Math.max(0, limit - elapsed)
  const anger = state?.anger ?? scenario.starting_anger
  const delta = previousAnger === null || !state ? 0 : state.anger - previousAnger
  const strikes = state?.strikes ?? 0
  const maxStrikes = state?.max_strikes ?? scenario.max_strikes
  const ending = state && state.status !== 'in_progress' ? outcome(state.status, state.last_tags) : null

  if (phase === 'failed') {
    return (
      <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-8">
        <Alert variant="destructive">
          <AlertTitle>The call couldn't connect</AlertTitle>
          <AlertDescription>{error || 'Check your connection and try again.'}</AlertDescription>
        </Alert>
        <div>
          <Button onClick={finish}>Back</Button>
        </div>
      </main>
    )
  }

  const status =
    phase === 'connecting'
      ? { label: 'Ringing', variant: 'primary-light' as const }
      : customerSpeaking
        ? { label: 'Speaking', variant: 'info-light' as const }
        : youSpeaking
          ? { label: 'Listening to you', variant: 'success-light' as const }
          : { label: 'On the line', variant: 'outline' as const }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col gap-4 px-4 py-6">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-3">
            <Avatar scenario={scenario} large />
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <CardTitle>{scenario.persona.name}</CardTitle>
              <div>
                <Badge variant={status.variant}>{status.label}</Badge>
              </div>
            </div>
            <div
              aria-label="Time left"
              className={cn(
                'text-2xl font-semibold tracking-tight tabular-nums',
                remaining <= 30 && 'text-destructive-foreground dark:text-destructive',
              )}
            >
              {clock(remaining)}
            </div>
          </div>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <AngerMeter anger={anger} />
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap gap-1" aria-live="polite">
              {delta !== 0 && (
                <Badge variant={delta < 0 ? 'success-light' : 'destructive-light'}>
                  {delta > 0 ? `+${delta}` : delta} anger
                </Badge>
              )}
              {state?.last_tags.map((tag) => (
                <Badge key={`${turn}-${tag}`} variant={isCalming(tag) ? 'success-light' : 'destructive-light'}>
                  {tagLabel(tag)}
                </Badge>
              ))}
            </div>
            <Badge variant={strikes > 0 ? 'destructive-light' : 'outline'}>
              Strikes {strikes}/{maxStrikes}
            </Badge>
          </div>
        </CardContent>
      </Card>

      {ending && (
        <Alert variant={state?.status === 'won' ? 'success' : 'warning'}>
          <AlertTitle>{ending.title}</AlertTitle>
          <AlertDescription>{ending.detail}</AlertDescription>
        </Alert>
      )}

      {showCaptions && (
        <Card className="min-h-0 flex-1">
          <CardContent className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto" aria-label="Captions" aria-live="polite">
            {captions.length === 0 && (
              <p className="text-sm text-muted-foreground" role="status">
                {phase === 'connecting' ? 'Connecting the call…' : 'The customer is about to speak…'}
              </p>
            )}
            {captions.map((caption) => (
              <div
                key={caption.id}
                className={cn('flex max-w-[85%] flex-col gap-0.5', caption.who === 'you' && 'self-end text-right')}
              >
                <span className="text-xs text-muted-foreground">
                  {caption.who === 'you' ? 'You' : scenario.persona.name}
                </span>
                <p className="text-sm">{caption.text}</p>
              </div>
            ))}
            <div ref={captionsEnd} />
          </CardContent>
        </Card>
      )}
      {!showCaptions && <div className="flex-1" />}

      <div className="flex flex-wrap items-center justify-center gap-2">
        {scenario.languages.length > 1 && (
          <div className="flex gap-1" role="group" aria-label="The language you speak">
            {scenario.languages.map((code) => (
              <Button
                key={code}
                variant="outline"
                aria-pressed={code === language}
                className={cn(code === language && 'bg-muted dark:bg-muted/50')}
                onClick={() => switchLanguage(code)}
                disabled={phase !== 'live'}
              >
                {LANGUAGES[code]?.native ?? code}
              </Button>
            ))}
          </div>
        )}
        <Button variant="outline" aria-pressed={showCaptions} onClick={() => setShowCaptions((on) => !on)}>
          <Captions data-icon="inline-start" />
          Captions {showCaptions ? 'on' : 'off'}
        </Button>
        <Button variant="destructive" onClick={hangUp} disabled={phase === 'ending'}>
          <PhoneOff data-icon="inline-start" />
          Hang up
        </Button>
      </div>
    </main>
  )
}

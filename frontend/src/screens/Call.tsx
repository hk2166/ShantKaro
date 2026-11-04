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

import { type CallState, offerEndpoint, type Scenario } from '../api.ts'
import { AngerMeter, Avatar, Spinner } from '../components.tsx'
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
  const [now, setNow] = useState(() => Date.now())

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
    setClockBase({ elapsed: update.elapsed_s, at: Date.now() })
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
      <main className="page narrow">
        <div className="notice error" role="alert">
          <strong>The call couldn't connect</strong>
          <p>{error || 'Check your connection and try again.'}</p>
        </div>
        <div className="actions">
          <button type="button" className="primary" onClick={finish}>
            Back
          </button>
        </div>
      </main>
    )
  }

  return (
    <main className="page narrow call">
      <section className="call-head">
        <div className={`speaker ${customerSpeaking ? 'speaking' : ''}`}>
          <Avatar scenario={scenario} size={64} />
        </div>
        <div className="call-who">
          <h1>{scenario.persona.name}</h1>
          <p className="muted">
            {phase === 'connecting'
              ? 'Ringing…'
              : customerSpeaking
                ? 'Speaking…'
                : youSpeaking
                  ? 'Listening to you…'
                  : 'On the line'}
          </p>
        </div>
        <div className={`timer ${remaining <= 30 ? 'low' : ''}`} aria-label="Time left">
          {clock(remaining)}
        </div>
      </section>

      <AngerMeter anger={anger} />

      <div className="call-status">
        <div key={turn} className="tags" aria-live="polite">
          {delta !== 0 && (
            <span className={`delta ${delta < 0 ? 'good' : 'bad'}`}>
              {delta > 0 ? `+${delta}` : delta} anger
            </span>
          )}
          {state?.last_tags.map((tag) => (
            <span key={tag} className={`tag ${isCalming(tag) ? 'good' : 'bad'}`}>
              {tagLabel(tag)}
            </span>
          ))}
        </div>
        <div className="strikes" aria-label={`${strikes} of ${maxStrikes} policy strikes`}>
          {Array.from({ length: maxStrikes }, (_, i) => (
            <span key={i} className={`strike ${i < strikes ? 'used' : ''}`} />
          ))}
          <span className="muted small">strikes</span>
        </div>
      </div>

      {ending && (
        <div className={`notice ${state?.status === 'won' ? 'success' : 'warn'}`} role="status">
          <strong>{ending.title}</strong>
          <p>{ending.detail}</p>
        </div>
      )}

      {phase === 'connecting' && <Spinner label="Connecting the call…" />}

      {showCaptions && (
        <section className="captions" aria-label="Captions" aria-live="polite">
          {captions.length === 0 && phase !== 'connecting' && (
            <p className="muted small">The customer is about to speak…</p>
          )}
          {captions.map((caption) => (
            <p key={caption.id} className={`bubble ${caption.who}`}>
              <span className="bubble-who">
                {caption.who === 'you' ? 'You' : scenario.persona.name}
              </span>
              {caption.text}
            </p>
          ))}
          <div ref={captionsEnd} />
        </section>
      )}

      <section className="call-controls">
        {scenario.languages.length > 1 && (
          <div className="segmented" role="group" aria-label="The language you speak">
            {scenario.languages.map((code) => (
              <button
                key={code}
                type="button"
                className={code === language ? 'on' : ''}
                aria-pressed={code === language}
                onClick={() => switchLanguage(code)}
                disabled={phase !== 'live'}
              >
                {LANGUAGES[code]?.native ?? code}
              </button>
            ))}
          </div>
        )}
        <button
          type="button"
          className="ghost"
          aria-pressed={showCaptions}
          onClick={() => setShowCaptions((on) => !on)}
        >
          Captions {showCaptions ? 'on' : 'off'}
        </button>
        <button
          type="button"
          className="danger"
          onClick={hangUp}
          disabled={phase === 'ending'}
        >
          Hang up
        </button>
      </section>
    </main>
  )
}

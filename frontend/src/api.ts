// Talks to the Shant Karo backend. In development, Vite forwards these paths to it
// (see vite.config.ts), so the browser only ever talks to one origin.

export type Scenario = {
  id: string
  title: string
  company: string
  industry: string
  persona: { name: string; age: number; city: string }
  summary: string
  /** Languages the trainee may speak; the first is the default. */
  languages: string[]
  customer_language: string
  allowed_remedies: string[]
  forbidden_promises: string[]
  time_limit_s: number
  starting_anger: number
  max_strikes: number
}

export type CallStatus = 'in_progress' | 'won' | 'hung_up' | 'timed_out' | 'ended_by_trainee'

/** Sent by the server after every turn, as an RTVI server message. */
export type CallState = {
  type: 'call_state'
  anger: number
  strikes: number
  max_strikes: number
  elapsed_s: number
  time_limit_s: number
  status: CallStatus
  last_tags: string[]
}

export type Line = { line: string; tags: string[]; anger_before: number; anger_after: number }

export type Tip = { quote: string; advice: string; try_saying: string }

export type Report = {
  session_id: string
  scenario: string
  status: CallStatus
  final_anger: number
  strikes: number
  turns: number
  total: number | null
  scores: {
    empathy: number
    resolution: number
    policy_compliance: number
    language_adaptation: number | null
    efficiency: number
  } | null
  best_line: Line | null
  worst_line: Line | null
  tips: Tip[]
}

/** The server refused to start a call: lines busy, daily limit, and so on. */
export class StartRefused extends Error {
  readonly code: string

  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

export async function fetchScenarios(): Promise<Scenario[]> {
  const response = await fetch('/scenarios')
  if (!response.ok) throw new Error(`Couldn't load the customers (${response.status})`)
  return response.json()
}

/** Ask the server for a call with this customer. Returns the session id to connect to. */
export async function startSession(scenarioId: string): Promise<string> {
  const response = await fetch('/start', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ transport: 'webrtc', body: { scenario: scenarioId } }),
  })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new StartRefused(
      data.error ?? 'error',
      data.message ?? "We couldn't start the call. Please try again.",
    )
  }
  return data.sessionId
}

export const offerEndpoint = (sessionId: string) => `/sessions/${sessionId}/api/offer`

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

/** The report card. The coach's tips take a few seconds, so this waits for them. */
export async function fetchReport(sessionId: string, signal?: AbortSignal): Promise<Report> {
  const deadline = Date.now() + 90_000
  while (Date.now() < deadline) {
    const response = await fetch(`/reports/${sessionId}`, { signal })
    if (response.status === 200) return response.json()
    if (response.status !== 202) throw new Error(`Couldn't load the report (${response.status})`)
    await sleep(1500)
  }
  throw new Error('The report is taking too long. Please try again.')
}

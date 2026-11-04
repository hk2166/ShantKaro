import type { CallStatus } from './api.ts'

/** What each of the Judge's tags means, in the trainee's words. */
export const TAGS: Record<string, { label: string; calming: boolean }> = {
  acknowledged_feeling: { label: 'Acknowledged feelings', calming: true },
  apologised: { label: 'Apologised', calming: true },
  used_name: { label: 'Used their name', calming: true },
  concrete_next_step: { label: 'Offered a real fix', calming: true },
  asked_clarifying_q: { label: 'Asked a good question', calming: true },
  followed_language_switch: { label: 'Switched language', calming: true },
  dismissive: { label: 'Dismissive', calming: false },
  blamed_customer: { label: 'Blamed the customer', calming: false },
  forbidden_promise: { label: 'Broke company policy', calming: false },
  manipulation_attempt: { label: 'Manipulative', calming: false },
  abusive: { label: 'Insulted the customer', calming: false },
}

export const tagLabel = (tag: string) => TAGS[tag]?.label ?? tag.replaceAll('_', ' ')
export const isCalming = (tag: string) => TAGS[tag]?.calming ?? false

export const LANGUAGES: Record<string, { name: string; native: string }> = {
  'en-IN': { name: 'English', native: 'English' },
  'hi-IN': { name: 'Hindi', native: 'हिन्दी' },
  'ta-IN': { name: 'Tamil', native: 'தமிழ்' },
}

export const languageName = (code: string) => LANGUAGES[code]?.name ?? code

/** The anger bands match the scenario files: 0–30, 31–60, 61–85, 86–100. */
export function mood(anger: number): { label: string; level: 'calm' | 'irritated' | 'angry' | 'furious' } {
  if (anger <= 30) return { label: 'Calming down', level: 'calm' }
  if (anger <= 60) return { label: 'Irritated', level: 'irritated' }
  if (anger <= 85) return { label: 'Angry', level: 'angry' }
  return { label: 'Furious', level: 'furious' }
}

export function outcome(status: CallStatus, lastTags: string[] = []): { title: string; detail: string } {
  switch (status) {
    case 'won':
      return { title: 'You calmed them down', detail: 'The customer accepted your fix.' }
    case 'hung_up':
      return lastTags.includes('abusive')
        ? { title: 'They hung up', detail: 'You insulted the customer. That ends a real call too.' }
        : { title: 'They hung up', detail: 'The customer ran out of patience.' }
    case 'timed_out':
      return { title: "Time's up", detail: 'Three minutes passed and the customer is still unhappy.' }
    case 'ended_by_trainee':
      return { title: 'You ended the call', detail: 'The customer was still on the line.' }
    default:
      return { title: 'Call in progress', detail: '' }
  }
}

export const clock = (seconds: number) => {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

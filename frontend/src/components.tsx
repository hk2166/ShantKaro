import type { Scenario } from './api.ts'
import { mood } from './labels.ts'

const AVATAR_HUES: Record<string, number> = { sharma_uncle: 28, lakshmi_aunty: 330, rohan: 205 }

export function Avatar({ scenario, size = 56 }: { scenario: Scenario; size?: number }) {
  const initials = scenario.persona.name
    .split(' ')
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
  const hue = AVATAR_HUES[scenario.id] ?? 260
  return (
    <div
      className="avatar"
      style={{ width: size, height: size, fontSize: size * 0.38, ['--hue' as string]: hue }}
      aria-hidden="true"
    >
      {initials}
    </div>
  )
}

/** The customer's anger, 0–100, as a bar coloured by mood. */
export function AngerMeter({ anger, size = 'large' }: { anger: number; size?: 'large' | 'small' }) {
  const { label, level } = mood(anger)
  return (
    <div className={`anger anger-${size} mood-${level}`}>
      {size === 'large' ? (
        <div className="anger-head">
          <span className="anger-label">{label}</span>
          <span className="anger-value">
            {anger}
            <small>/100 anger</small>
          </span>
        </div>
      ) : (
        <div className="anger-head small">
          <span className="anger-label">Starts {label.toLowerCase()}</span>
          <span className="muted">{anger}/100 anger</span>
        </div>
      )}
      <div
        className="anger-track"
        role="meter"
        aria-label="Customer anger"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={anger}
        aria-valuetext={`${anger} out of 100, ${label}`}
      >
        <div className="anger-fill" style={{ width: `${anger}%` }} />
        <div className="anger-goal" title="Get the anger to 20 or below, with a fix agreed" />
      </div>
    </div>
  )
}

export function Spinner({ label }: { label: string }) {
  return (
    <div className="spinner" role="status">
      <span className="spinner-dot" />
      {label}
    </div>
  )
}

import type { Scenario } from '../api.ts'
import { AngerMeter, Avatar } from '../components.tsx'
import { languageName } from '../labels.ts'

// Sharma Uncle first: he's the flagship, and Hinglish is what most trainees speak.
const ORDER = ['sharma_uncle', 'lakshmi_aunty', 'rohan']
const rank = (scenario: Scenario) => {
  const index = ORDER.indexOf(scenario.id)
  return index === -1 ? ORDER.length : index
}

export function Picker({
  scenarios,
  onPick,
}: {
  scenarios: Scenario[]
  onPick: (scenario: Scenario) => void
}) {
  const sorted = [...scenarios].sort((a, b) => rank(a) - rank(b))
  return (
    <main className="page">
      <header className="hero">
        <p className="eyebrow">Call-centre training · by voice</p>
        <h1>
          Shant Karo <span className="hero-native">शांत करो</span>
        </h1>
        <p className="lede">
          An angry customer is on the line. You have three minutes to calm them down, without
          promising anything your company doesn't allow.
        </p>
      </header>

      <h2 className="section-title">Pick a customer</h2>
      <ul className="cards">
        {sorted.map((scenario) => (
          <li key={scenario.id}>
            <button type="button" className="card persona" onClick={() => onPick(scenario)}>
              <div className="persona-top">
                <Avatar scenario={scenario} />
                <div>
                  <h3>{scenario.persona.name}</h3>
                  <p className="muted">
                    {scenario.persona.age} · {scenario.persona.city}
                  </p>
                </div>
              </div>
              <p className="persona-company">
                {scenario.company} <span className="muted">· {scenario.industry}</span>
              </p>
              <p className="persona-summary">{scenario.summary}</p>
              <p className="chips">
                <span className="chip">Speaks {languageName(scenario.customer_language)}</span>
                {scenario.languages.length > 1 && (
                  <span className="chip">
                    You can reply in {scenario.languages.map(languageName).join(' or ')}
                  </span>
                )}
              </p>
              <AngerMeter anger={scenario.starting_anger} size="small" />
              <span className="persona-cta">Take the call →</span>
            </button>
          </li>
        ))}
      </ul>

      <footer className="footnote">
        The customers are AI and every company is made up. Your voice is turned into text to play
        the game; no audio is stored. Headphones work best.
      </footer>
    </main>
  )
}

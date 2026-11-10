import { ArrowRight, RotateCw, Users } from 'lucide-react'

import type { Scenario } from '../api.ts'
import { AngerMeter, Avatar, ScenarioCardSkeleton } from '../components.tsx'
import { Alert, AlertAction, AlertDescription, AlertTitle } from '../components/reui/alert.tsx'
import { Badge } from '../components/reui/badge.tsx'
import { Button } from '../components/ui/button.tsx'
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '../components/ui/card.tsx'
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from '../components/ui/empty.tsx'
import { languageName } from '../labels.ts'

// Sharma Uncle first: he's the flagship, and Hinglish is what most trainees speak.
const ORDER = ['sharma_uncle', 'lakshmi_aunty', 'rohan']
const rank = (scenario: Scenario) => {
  const index = ORDER.indexOf(scenario.id)
  return index === -1 ? ORDER.length : index
}

export function Picker({
  scenarios,
  error,
  onRetry,
  onPick,
}: {
  scenarios: Scenario[] | null
  error: string
  onRetry: () => void
  onPick: (scenario: Scenario) => void
}) {
  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-8 px-4 py-10">
      <header className="flex max-w-2xl flex-col gap-3">
        <Badge variant="outline">Call-centre training, by voice</Badge>
        <h1 className="text-4xl font-semibold tracking-tight">
          Shant Karo <span className="text-muted-foreground">शांत करो</span>
        </h1>
        <p className="text-muted-foreground">
          An angry customer is on the line. Calm them down in three minutes, without promising
          anything your company doesn't allow.
        </p>
      </header>

      <section className="flex flex-col gap-4" aria-labelledby="pick-title">
        <h2 id="pick-title" className="text-sm font-medium text-muted-foreground">
          Pick a customer
        </h2>

        {error && (
          <Alert variant="destructive">
            <AlertTitle>The training centre is closed right now</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
            <AlertAction>
              <Button variant="outline" size="sm" onClick={onRetry}>
                <RotateCw data-icon="inline-start" />
                Retry
              </Button>
            </AlertAction>
          </Alert>
        )}

        {!error && !scenarios && (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3" role="status" aria-label="Loading the customers">
            <ScenarioCardSkeleton />
            <ScenarioCardSkeleton />
            <ScenarioCardSkeleton />
          </div>
        )}

        {scenarios && scenarios.length === 0 && (
          <Empty>
            <EmptyHeader>
              <EmptyMedia variant="icon">
                <Users />
              </EmptyMedia>
              <EmptyTitle>No customers today</EmptyTitle>
              <EmptyDescription>The scenarios didn't load. Try again in a moment.</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button variant="outline" onClick={onRetry}>
                Retry
              </Button>
            </EmptyContent>
          </Empty>
        )}

        {scenarios && scenarios.length > 0 && (
          <ul className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {[...scenarios]
              .sort((a, b) => rank(a) - rank(b))
              .map((scenario) => (
                <li key={scenario.id} className="flex">
                  <PersonaCard scenario={scenario} onPick={onPick} />
                </li>
              ))}
          </ul>
        )}
      </section>

      <p className="max-w-2xl text-xs text-muted-foreground">
        The customers are AI and every company is made up. Your voice is turned into text to play
        the game; no audio is stored. Headphones work best.
      </p>
    </main>
  )
}

function PersonaCard({ scenario, onPick }: { scenario: Scenario; onPick: (s: Scenario) => void }) {
  return (
    <Card className="w-full">
      <CardHeader>
        <div className="flex items-center gap-3">
          <Avatar scenario={scenario} />
          <div className="flex min-w-0 flex-col gap-0.5">
            <CardTitle>{scenario.persona.name}</CardTitle>
            <CardDescription>
              {scenario.persona.age}, {scenario.persona.city}
            </CardDescription>
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-3">
        <p className="text-sm font-medium">
          {scenario.company} <span className="font-normal text-muted-foreground">({scenario.industry})</span>
        </p>
        <p className="flex-1 text-sm text-muted-foreground">{scenario.summary}</p>
        <div className="flex flex-wrap gap-1">
          <Badge variant="outline">Speaks {languageName(scenario.customer_language)}</Badge>
          {scenario.languages.length > 1 && (
            <Badge variant="outline">
              Reply in {scenario.languages.map(languageName).join(' or ')}
            </Badge>
          )}
        </div>
        <AngerMeter anger={scenario.starting_anger} label="Starting anger" />
      </CardContent>
      <CardFooter>
        <Button className="w-full" onClick={() => onPick(scenario)}>
          Take the call
          <ArrowRight data-icon="inline-end" />
        </Button>
      </CardFooter>
    </Card>
  )
}

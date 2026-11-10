import { cn } from '@/lib/utils'

import type { Scenario } from './api.ts'
import { Card, CardContent, CardHeader } from './components/ui/card.tsx'
import { Progress, ProgressLabel, ProgressValue } from './components/ui/progress.tsx'
import { Skeleton } from './components/ui/skeleton.tsx'
import { mood } from './labels.ts'

// Each customer's avatar colour is identity, not state, so it uses the raw palette.
const AVATAR_COLORS: Record<string, string> = {
  sharma_uncle: 'bg-amber-100 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200',
  lakshmi_aunty: 'bg-pink-100 text-pink-900 dark:bg-pink-900/40 dark:text-pink-200',
  rohan: 'bg-sky-100 text-sky-900 dark:bg-sky-900/40 dark:text-sky-200',
}

export function Avatar({ scenario, large = false }: { scenario: Scenario; large?: boolean }) {
  const initials = scenario.persona.name
    .split(' ')
    .map((word) => word[0])
    .join('')
    .slice(0, 2)
  return (
    <div
      aria-hidden="true"
      className={cn(
        'flex shrink-0 items-center justify-center rounded-full font-semibold',
        large ? 'size-14 text-lg' : 'size-10 text-sm',
        AVATAR_COLORS[scenario.id] ?? 'bg-muted text-foreground',
      )}
    >
      {initials}
    </div>
  )
}

// The anger bands are the customer's mood, shown as a colour scale from calm to furious.
const MOOD_FILL: Record<ReturnType<typeof mood>['level'], string> = {
  calm: '[&_[data-slot=progress-indicator]]:bg-emerald-500 dark:[&_[data-slot=progress-indicator]]:bg-emerald-400',
  irritated: '[&_[data-slot=progress-indicator]]:bg-amber-500 dark:[&_[data-slot=progress-indicator]]:bg-amber-400',
  angry: '[&_[data-slot=progress-indicator]]:bg-orange-500 dark:[&_[data-slot=progress-indicator]]:bg-orange-400',
  furious: '[&_[data-slot=progress-indicator]]:bg-red-600 dark:[&_[data-slot=progress-indicator]]:bg-red-500',
}

/** The customer's anger, 0–100. The win line is 20 or below. */
export function AngerMeter({ anger, label }: { anger: number; label?: string }) {
  const current = mood(anger)
  return (
    <Progress value={anger} className={MOOD_FILL[current.level]}>
      <ProgressLabel>{label ?? current.label}</ProgressLabel>
      <ProgressValue>{(_, value) => `${value ?? anger}/100 anger`}</ProgressValue>
    </Progress>
  )
}

export function ScenarioCardSkeleton() {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-center gap-3">
          <Skeleton className="size-10 rounded-full" />
          <div className="flex flex-1 flex-col gap-1.5">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-20" />
          </div>
        </div>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-2 w-full" />
      </CardContent>
    </Card>
  )
}

"use client"

import * as React from "react"

import { Input } from "@/components/ui/input"
import {
  HOURLY_PROFILE_LENGTH,
  parseHourlyProfile,
  serializeHourlyProfile,
} from "@/lib/hourly-profile"
import { cn } from "@/lib/utils"

const HOURS = Array.from({ length: HOURLY_PROFILE_LENGTH }, (_, hour) => hour)

interface HourlyProfileEditorProps {
  value?: string
  onChange: (value: string) => void
  copyValue?: string
  copyLabel?: string
  emptyHint: string
  className?: string
}

function formatHour(hour: number): string {
  return `${String(hour).padStart(2, "0")}:00`
}

function makeProfile(value: number): number[] {
  return Array.from({ length: HOURLY_PROFILE_LENGTH }, () => value)
}

function makeWorkingHoursProfile(startHour = 7, endHour = 18): number[] {
  return HOURS.map((hour) => (hour >= startHour && hour < endHour ? 1 : 0))
}

const actionClassName =
  "rounded-md border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:border-slate-400 hover:bg-slate-50"

export function HourlyProfileEditor({
  value,
  onChange,
  copyValue,
  copyLabel = "Powiel dni robocze",
  emptyHint,
  className,
}: HourlyProfileEditorProps) {
  const parsedValue = parseHourlyProfile(value)
  const [draftValues, setDraftValues] = React.useState<number[]>(
    () => parsedValue ?? makeProfile(0),
  )
  const isActive = parsedValue !== undefined
  const isInvalid = Boolean(value?.trim()) && !isActive
  const parsedCopyValue = parseHourlyProfile(copyValue)

  React.useEffect(() => {
    const nextProfile = parseHourlyProfile(value)
    if (nextProfile) setDraftValues(nextProfile)
  }, [value])

  const updateProfile = (values: number[]) => {
    setDraftValues(values)
    onChange(serializeHourlyProfile(values))
  }

  const updateHour = (hour: number, nextValue: string) => {
    const numericValue = Number(nextValue)
    if (!Number.isFinite(numericValue)) return

    const boundedValue = Math.min(1, Math.max(0, numericValue))
    const nextProfile = [...draftValues]
    nextProfile[hour] = boundedValue
    updateProfile(nextProfile)
  }

  return (
    <div className={cn("space-y-3", className)}>
      <div className="flex flex-col gap-2 rounded-md border border-slate-200 bg-slate-50 p-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-medium text-slate-800">
            {isActive ? "Profil aktywny" : "Profil nieustawiony"}
          </p>
          <p className="text-xs text-slate-600">
            {isInvalid
              ? "Obecny zapis nie zawiera 24 poprawnych wartości. Otwórz edytor, aby go zastąpić."
              : emptyHint}
          </p>
        </div>
        <button
          type="button"
          className={actionClassName}
          onClick={() => {
            if (isActive) {
              onChange("")
              return
            }
            updateProfile(draftValues)
          }}
        >
          {isActive ? "Wyłącz profil" : "Włącz edytor 24 godzin"}
        </button>
      </div>

      {isActive ? (
        <div className="space-y-3 rounded-md border border-slate-200 p-3">
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6 md:grid-cols-8 lg:grid-cols-12">
            {HOURS.map((hour) => (
              <label key={hour} className="space-y-1 text-center">
                <span className="block text-[11px] font-medium text-slate-500">
                  {formatHour(hour)}
                </span>
                <Input
                  aria-label={`Wartość profilu dla godziny ${formatHour(hour)}`}
                  type="number"
                  min="0"
                  max="1"
                  step="0.01"
                  value={draftValues[hour]}
                  onChange={(event) => updateHour(hour, event.target.value)}
                  className="h-9 px-1 text-center"
                />
              </label>
            ))}
          </div>

          <div className="flex flex-wrap gap-2 border-t border-slate-100 pt-3">
            <button type="button" className={actionClassName} onClick={() => updateProfile(makeProfile(0))}>
              Wyłącz cały dzień
            </button>
            <button type="button" className={actionClassName} onClick={() => updateProfile(makeProfile(1))}>
              Włącz cały dzień
            </button>
            <button
              type="button"
              className={actionClassName}
              onClick={() => updateProfile(makeWorkingHoursProfile())}
            >
              Godziny pracy 07:00–18:00
            </button>
            {parsedCopyValue ? (
              <button
                type="button"
                className={actionClassName}
                onClick={() => updateProfile(parsedCopyValue)}
              >
                {copyLabel}
              </button>
            ) : null}
          </div>

          <p className="text-xs text-slate-500">
            Wpisz wartość od 0 do 1 dla każdej godziny. 0 oznacza wyłączenie, 1 pełną pracę,
            a wartości pośrednie częściowe użytkowanie.
          </p>
        </div>
      ) : null}
    </div>
  )
}

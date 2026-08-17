export const HOURLY_PROFILE_LENGTH = 24

function parseTokens(value: string): number[] | undefined {
  const tokens = value.split(/[\s,;]+/).filter(Boolean)
  if (tokens.length !== HOURLY_PROFILE_LENGTH) return undefined

  const profile = tokens.map(Number)
  if (!profile.every((item) => Number.isFinite(item) && item >= 0 && item <= 1)) {
    return undefined
  }

  return profile
}

export function parseHourlyProfile(value: string | undefined): number[] | undefined {
  if (!value?.trim()) return undefined
  return parseTokens(value.trim())
}

export function serializeHourlyProfile(values: readonly number[]): string {
  if (values.length !== HOURLY_PROFILE_LENGTH) {
    throw new Error(`Hourly profile must contain exactly ${HOURLY_PROFILE_LENGTH} values`)
  }

  return values.map((value) => Number(value.toFixed(2))).join(" ")
}

/**
 * Keeps old/imported projects usable when a user entered a single 0 or 1
 * intending the same value for every hour of a day.
 */
export function normalizeHourlyProfileInput(value: unknown): string {
  if (typeof value !== "string") return ""

  const trimmed = value.trim()
  if (!trimmed) return ""

  const tokens = trimmed.split(/[\s,;]+/).filter(Boolean)
  if (tokens.length !== 1) return value

  const singleValue = Number(tokens[0])
  if (!Number.isFinite(singleValue) || singleValue < 0 || singleValue > 1) return value

  return serializeHourlyProfile(Array.from({ length: HOURLY_PROFILE_LENGTH }, () => singleValue))
}

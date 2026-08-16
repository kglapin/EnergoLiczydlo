import { BuildingProject, CalculationResult } from "./store"

export interface ApiValidationIssue {
  loc: Array<string | number>
  msg: string
  type?: string
  ctx?: Record<string, unknown>
}

export class CalculationRequestError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly validationIssues: ApiValidationIssue[] = [],
  ) {
    super(message)
    this.name = "CalculationRequestError"
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function parseValidationIssues(value: unknown): ApiValidationIssue[] {
  if (!Array.isArray(value)) return []

  return value.flatMap((issue) => {
    if (!isRecord(issue) || !Array.isArray(issue.loc) || typeof issue.msg !== "string") {
      return []
    }

    const loc = issue.loc.filter(
      (part): part is string | number => typeof part === "string" || typeof part === "number",
    )
    if (loc.length === 0) return []

    return [{
      loc,
      msg: issue.msg,
      type: typeof issue.type === "string" ? issue.type : undefined,
      ctx: isRecord(issue.ctx) ? issue.ctx : undefined,
    }]
  })
}

function errorMessage(data: unknown): string {
  if (!isRecord(data)) return "Serwer zwrócił nieprawidłową odpowiedź."
  if (typeof data.detail === "string") return data.detail
  if (typeof data.error === "string") return data.error
  return "Dane wejściowe nie spełniają wymagań obliczeń."
}

export interface ClimateStation {
  id: string
  name: string
  latitude: number
  longitude: number
}

export interface ClimateLocationResolution {
  query: string
  matched_location: string
  latitude: number
  longitude: number
  station: ClimateStation & {
    distance_km: number
  }
}

export async function calculate(project: BuildingProject): Promise<CalculationResult> {
  const res = await fetch("/api/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  })
  const data: unknown = await res.json()
  if (!res.ok) {
    throw new CalculationRequestError(
      errorMessage(data),
      res.status,
      parseValidationIssues(isRecord(data) ? data.detail : undefined),
    )
  }
  return data as CalculationResult
}

export async function fetchStations(): Promise<ClimateStation[]> {
  const res = await fetch("/api/stations", { cache: "no-store" })
  const data = await res.json()
  if (!res.ok) {
    const text = data.error || JSON.stringify(data)
    throw new Error(`Failed to fetch stations: ${res.status} ${text}`)
  }
  return data
}

export async function resolveClimateStation(
  location: string
): Promise<ClimateLocationResolution> {
  const params = new URLSearchParams({ location })
  const res = await fetch(`/api/stations/resolve-location?${params.toString()}`, {
    cache: "no-store",
  })
  const data = await res.json()
  if (!res.ok) {
    const text = data.error || JSON.stringify(data)
    throw new Error(`Nie udało się dobrać stacji: ${text}`)
  }
  return data
}

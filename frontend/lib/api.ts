import { BuildingProject, CalculationResult } from "./store"

export async function calculate(project: BuildingProject): Promise<CalculationResult> {
  const res = await fetch("/api/calculate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  })
  const data = await res.json()
  if (!res.ok) {
    const text = data.detail || data.error || JSON.stringify(data)
    throw new Error(`Calculation failed: ${res.status} ${text}`)
  }
  return data
}

export async function fetchStations(): Promise<Array<{ id: string; name: string }>> {
  const res = await fetch("/api/stations", { cache: "no-store" })
  const data = await res.json()
  if (!res.ok) {
    const text = data.error || JSON.stringify(data)
    throw new Error(`Failed to fetch stations: ${res.status} ${text}`)
  }
  return data
}

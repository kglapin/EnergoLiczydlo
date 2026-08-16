import { BuildingProject, CalculationResult } from "./store"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"

export async function calculate(project: BuildingProject): Promise<CalculationResult> {
  const res = await fetch(`${API_URL}/api/calculate/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(project),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`Calculation failed: ${res.status} ${text}`)
  }
  return res.json()
}

export async function fetchStations(): Promise<Array<{ id: string; name: string }>> {
  const res = await fetch(`${API_URL}/api/climate/stations`)
  if (!res.ok) {
    throw new Error("Failed to fetch stations")
  }
  return res.json()
}

import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_API_URL || "http://127.0.0.1:8000"

export async function GET(request: NextRequest) {
  const location = request.nextUrl.searchParams.get("location")?.trim()
  if (!location) {
    return NextResponse.json({ error: "Brak lokalizacji" }, { status: 400 })
  }

  const backendUrl = new URL(`${BACKEND_URL}/api/climate/resolve-location`)
  backendUrl.searchParams.set("location", location)

  try {
    const res = await fetch(backendUrl, { cache: "no-store" })
    const data = await res.json()
    if (!res.ok) {
      return NextResponse.json(
        { error: data.detail || data.error || "Nie udało się dobrać stacji" },
        { status: res.status }
      )
    }
    return NextResponse.json(data)
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error"
    return NextResponse.json(
      { error: `Failed to reach backend: ${message}` },
      { status: 502 }
    )
  }
}

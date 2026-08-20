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
    const text = await res.text()
    let data: unknown = null
    if (text) {
      try {
        data = JSON.parse(text)
      } catch {
        // Backend zwrócił odpowiedź niebędącą JSON-em (np. plain-text 500).
        return NextResponse.json(
          {
            error:
              "Backend zwrócił nieprawidłową odpowiedź. Sprawdź, czy usługa backendowa działa poprawnie.",
          },
          { status: 502 }
        )
      }
    }

    if (!res.ok) {
      const detail =
        typeof data === "object" &&
        data !== null &&
        ("detail" in data || "error" in data)
          ? ((data as { detail?: string; error?: string }).detail ??
            (data as { error?: string }).error)
          : undefined
      return NextResponse.json(
        { error: detail || "Nie udało się dobrać stacji" },
        { status: res.status }
      )
    }
    return NextResponse.json(data)
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error"
    return NextResponse.json(
      {
        error: `Nie udało się połączyć z backendem: ${message}. Sprawdź, czy usługa backendowa jest uruchomiona.`,
      },
      { status: 502 }
    )
  }
}

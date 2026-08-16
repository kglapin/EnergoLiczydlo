import { NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_API_URL || "http://127.0.0.1:8000"

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/api/climate/stations`, {
      cache: "no-store",
    })
    if (!res.ok) {
      return NextResponse.json(
        { error: "Backend returned an error" },
        { status: res.status }
      )
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unknown error"
    return NextResponse.json(
      { error: `Failed to reach backend: ${message}` },
      { status: 502 }
    )
  }
}

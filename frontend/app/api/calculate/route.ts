import { NextRequest, NextResponse } from "next/server"

const BACKEND_URL = process.env.BACKEND_API_URL || "http://127.0.0.1:8000"

export async function POST(request: NextRequest) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND_URL}/api/calculate/`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })

    const data = await res.json()
    if (!res.ok) {
      return NextResponse.json(data, { status: res.status })
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

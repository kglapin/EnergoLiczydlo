"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

import { Button } from "@/components/ui/button"
import { useAppStore } from "@/lib/store"
import { CalculationResults } from "@/components/calculation-results"

export default function ResultsPage() {
  const router = useRouter()
  const { result, project, startNewProject } = useAppStore()

  useEffect(() => {
    if (!result) {
      router.push("/building")
    }
  }, [result, router])

  if (!result) {
    return null
  }

  return (
    <main className="container mx-auto py-8 px-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Wyniki obliczeń</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push("/building")}>
            Edytuj dane
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              startNewProject()
              router.push("/building?new=1")
            }}
          >
            Nowa analiza
          </Button>
        </div>
      </div>

      <CalculationResults result={result} project={project} />
    </main>
  )
}

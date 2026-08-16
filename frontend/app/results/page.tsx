"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { useAppStore } from "@/lib/store"
import { ResultsChart } from "@/components/results-chart"
import { ResultsTable } from "@/components/results-table"

export default function ResultsPage() {
  const router = useRouter()
  const { result, project, reset } = useAppStore()

  useEffect(() => {
    if (!result) {
      router.push("/building")
    }
  }, [result, router])

  if (!result) {
    return null
  }

  const indicators = result.annual_indicators

  return (
    <main className="container mx-auto py-8 px-4">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-3xl font-bold">Wyniki obliczeń</h1>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => router.push("/building")}>
            Edytuj dane
          </Button>
          <Button variant="secondary" onClick={reset}>
            Nowa analiza
          </Button>
        </div>
      </div>

      {project && (
        <p className="text-muted-foreground mb-6">
          Projekt: <span className="font-medium text-foreground">{project.project_name}</span>
        </p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Energia użytkowa Eu
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.eu_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Energia końcowa Ek
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.ek_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Energia pierwotna Ep
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.ep_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Ogrzewanie</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.heating_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">Chłodzenie</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.cooling_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">C.W.U.</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">{indicators.dhw_kwh_m2_year.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">kWh/(m²·rok)</p>
          </CardContent>
        </Card>
      </div>

      <h2 className="text-xl font-semibold mb-4">Ocena zgodności</h2>
      <div className="grid grid-cols-1 gap-2 mb-8">
        {result.compliance.map((check) => (
          <Alert key={check.name} variant={check.passed ? "default" : "destructive"}>
            <AlertTitle className="flex items-center gap-2">
              {check.name}
              <Badge variant={check.passed ? "default" : "destructive"}>
                {check.passed ? "OK" : "NIE"}
              </Badge>
            </AlertTitle>
            <AlertDescription>{check.message}</AlertDescription>
          </Alert>
        ))}
      </div>

      <h2 className="text-xl font-semibold mb-4">Miesięczne wyniki</h2>
      <div className="mb-8">
        <ResultsChart data={result.monthly} />
      </div>
      <div className="overflow-x-auto">
        <ResultsTable data={result.monthly} />
      </div>
    </main>
  )
}

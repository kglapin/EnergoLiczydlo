import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { ResultsChart } from "@/components/results-chart"
import { ResultsTable } from "@/components/results-table"
import type { BuildingProject, CalculationResult } from "@/lib/store"

interface CalculationResultsProps {
  result: CalculationResult
  project: BuildingProject | null
}

export function CalculationResults({ result, project }: CalculationResultsProps) {
  const indicators = result.annual_indicators

  return (
    <section aria-labelledby="calculation-results-heading">
      <div className="mb-6">
        <h2 id="calculation-results-heading" className="text-3xl font-bold">
          Wyniki obliczeń
        </h2>
        {project && (
          <p className="mt-2 text-muted-foreground">
            Projekt: <span className="font-medium text-foreground">{project.project_name}</span>
          </p>
        )}
      </div>

      {typeof result.design_heating_power_kw === "number" && project?.systems?.heating?.system_type !== "none" && (
        <Card className="mb-8 border-primary/30 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Dobór mocy źródła ciepła
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-3xl font-bold">
              {result.design_heating_power_kw.toFixed(1)}
            </div>
            <p className="text-xs text-muted-foreground">
              kW mocy cieplnej — szczytowe straty przez przenikanie i wentylację
            </p>
          </CardContent>
        </Card>
      )}

      <div className="mb-8 grid grid-cols-1 gap-4 md:grid-cols-3">
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

      <h3 className="mb-4 text-xl font-semibold">Ocena zgodności</h3>
      <div className="mb-8 grid grid-cols-1 gap-2">
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

      <h3 className="mb-4 text-xl font-semibold">Miesięczne wyniki</h3>
      <div className="mb-8">
        <ResultsChart data={result.monthly} />
      </div>
      <div className="overflow-x-auto">
        <ResultsTable data={result.monthly} />
      </div>
    </section>
  )
}

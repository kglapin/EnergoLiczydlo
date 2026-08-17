import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  AlertTriangle,
  BarChart3,
  CheckCircle2,
  Droplets,
  Gauge,
  Leaf,
  Snowflake,
  Thermometer,
  Zap,
  type LucideIcon,
} from "lucide-react"
import { ResultsChart } from "@/components/results-chart"
import { ResultsTable } from "@/components/results-table"
import type { BuildingProject, CalculationResult } from "@/lib/store"

interface CalculationResultsProps {
  result: CalculationResult
  project: BuildingProject | null
}

type ResultsSectionHeaderProps = {
  icon: LucideIcon
  eyebrow: string
  title: string
  description: string
  iconClassName: string
}

function ResultsSectionHeader({
  icon: Icon,
  eyebrow,
  title,
  description,
  iconClassName,
}: ResultsSectionHeaderProps) {
  return (
    <div className="flex items-start gap-3">
      <div className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl ${iconClassName}`}>
        <Icon className="h-5 w-5" aria-hidden="true" />
      </div>
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">{eyebrow}</p>
        <h3 className="mt-1 text-xl font-semibold tracking-tight text-slate-950">{title}</h3>
        <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
      </div>
    </div>
  )
}

type MetricCardProps = {
  label: string
  value: number
  icon: LucideIcon
  iconClassName: string
  accentClassName: string
}

function MetricCard({ label, value, icon: Icon, iconClassName, accentClassName }: MetricCardProps) {
  return (
    <Card className={`overflow-hidden border-slate-200 border-l-4 shadow-sm ${accentClassName}`}>
      <CardContent className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-slate-600">{label}</p>
            <p className="mt-3 text-3xl font-bold tracking-tight text-slate-950">{value.toFixed(1)}</p>
            <p className="mt-1 text-xs text-slate-500">kWh/(m²·rok)</p>
          </div>
          <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${iconClassName}`}>
            <Icon className="h-4 w-4" aria-hidden="true" />
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export function CalculationResults({ result, project }: CalculationResultsProps) {
  const indicators = result.annual_indicators

  return (
    <section aria-labelledby="calculation-results-heading" className="space-y-6">
      <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-600">Analiza zakończona</p>
            <h2 id="calculation-results-heading" className="mt-1 text-3xl font-bold tracking-tight text-slate-950">
              Wyniki obliczeń
            </h2>
            {project && (
              <p className="mt-2 text-sm text-slate-600">
                Projekt: <span className="font-semibold text-slate-950">{project.project_name}</span>
              </p>
            )}
          </div>
          <div className="flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-700">
            <CheckCircle2 className="h-4 w-4" aria-hidden="true" />
            Wynik dostępny
          </div>
        </div>
      </div>

      {typeof result.design_heating_power_kw === "number" && project?.systems?.heating?.system_type !== "none" && (
        <Card className="overflow-hidden border-amber-200 bg-gradient-to-br from-amber-50 to-white shadow-sm">
          <CardContent className="flex items-start gap-4 p-5 md:p-6">
            <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
              <Thermometer className="h-5 w-5" aria-hidden="true" />
            </div>
            <div>
              <p className="text-sm font-semibold text-amber-950">Diagnostyczna szczytowa strata ciepła</p>
              <div className="mt-1 flex items-baseline gap-2">
                <span className="text-3xl font-bold tracking-tight text-slate-950">{result.design_heating_power_kw.toFixed(1)}</span>
                <span className="text-sm font-medium text-slate-600">kW</span>
              </div>
              <p className="mt-1 max-w-3xl text-xs leading-5 text-slate-600">
                Maksimum strat przez przenikanie i wentylację w wybranym roku TMY. Ta wartość nie zastępuje
                odrębnego obliczenia projektowego obciążenia cieplnego dla temperatury obliczeniowej.
              </p>
            </div>
          </CardContent>
        </Card>
      )}

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
        <ResultsSectionHeader
          icon={Gauge}
          eyebrow="Wskaźniki roczne"
          title="Bilans energetyczny"
          description="Najważniejsze wartości jednostkowe dla analizowanego budynku."
          iconClassName="bg-blue-100 text-blue-700"
        />
        <div className="mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <MetricCard label="Energia użytkowa Eu" value={indicators.eu_kwh_m2_year} icon={Gauge} iconClassName="bg-blue-100 text-blue-700" accentClassName="border-l-blue-500" />
          <MetricCard label="Energia końcowa Ek" value={indicators.ek_kwh_m2_year} icon={Zap} iconClassName="bg-emerald-100 text-emerald-700" accentClassName="border-l-emerald-500" />
          <MetricCard label="Energia pierwotna Ep" value={indicators.ep_kwh_m2_year} icon={Leaf} iconClassName="bg-violet-100 text-violet-700" accentClassName="border-l-violet-500" />
          <MetricCard label="Ogrzewanie" value={indicators.heating_kwh_m2_year} icon={Thermometer} iconClassName="bg-orange-100 text-orange-700" accentClassName="border-l-orange-500" />
          <MetricCard label="Chłodzenie" value={indicators.cooling_kwh_m2_year} icon={Snowflake} iconClassName="bg-cyan-100 text-cyan-700" accentClassName="border-l-cyan-500" />
          <MetricCard label="Ciepła woda użytkowa" value={indicators.dhw_kwh_m2_year} icon={Droplets} iconClassName="bg-sky-100 text-sky-700" accentClassName="border-l-sky-500" />
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
        <ResultsSectionHeader
          icon={AlertTriangle}
          eyebrow="Kontrola jakości"
          title="Założenia, ostrzeżenia i kontrole"
          description="Silnik pokazuje tu zarówno kontrole wyniku, jak i dane przyjęte automatycznie lub ograniczenia modelu."
          iconClassName="bg-amber-100 text-amber-700"
        />
        <div className="mt-5 grid grid-cols-1 gap-3">
          {result.compliance.map((check) => {
            const isAuditWarning = check.name.startsWith("Ostrzeżenie audytowe:")
            const isAuditInfo = check.name.startsWith("Informacja audytowa:")
            return (
              <Alert
                key={check.name}
                variant={!check.passed && !isAuditWarning ? "destructive" : "default"}
                className={isAuditWarning ? "border-amber-300 bg-amber-50 text-amber-950" : undefined}
              >
                <AlertTitle className="flex flex-wrap items-center gap-2">
                  {check.name}
                  <Badge
                    variant={!check.passed && !isAuditWarning ? "destructive" : "default"}
                    className={isAuditWarning ? "bg-amber-600 text-white hover:bg-amber-600" : undefined}
                  >
                    {isAuditWarning ? "UWAGA" : isAuditInfo ? "INFO" : check.passed ? "OK" : "NIE"}
                  </Badge>
                </AlertTitle>
                <AlertDescription>{check.message}</AlertDescription>
              </Alert>
            )
          })}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm md:p-6">
        <ResultsSectionHeader
          icon={BarChart3}
          eyebrow="Przebieg w roku"
          title="Miesięczne wyniki"
          description="Porównaj zapotrzebowanie na ogrzewanie, chłodzenie, CWU i zyski słoneczne."
          iconClassName="bg-amber-100 text-amber-700"
        />
        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50/60 p-3 md:p-4">
          <ResultsChart data={result.monthly} />
        </div>
        <div className="mt-5 overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <ResultsTable data={result.monthly} />
        </div>
      </section>
    </section>
  )
}

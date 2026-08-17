"use client"

import Link from "next/link"
import { ArrowLeft } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { useAppStore, type BuildingProject } from "@/lib/store"

type Factor = { fp: number; we: number }
type ProjectWithPrimaryEnergy = BuildingProject & {
  primary_energy?: Record<string, Factor>
}

const FALLBACK_FACTORS: Record<string, Factor> = {
  electricity: { fp: 2.5, we: 0.6 },
  natural_gas: { fp: 1.1, we: 0.2 },
  lpg: { fp: 1.1, we: 0.2 },
  heating_oil: { fp: 1.1, we: 0.27 },
  hard_coal: { fp: 1.1, we: 0.34 },
  lignite: { fp: 1.1, we: 0.34 },
  district_heating: { fp: 1.2, we: 0.25 },
  biomass: { fp: 0.2, we: 0.05 },
  biogas: { fp: 0.5, we: 0.05 },
  solar: { fp: 0.0, we: 0.0 },
  wind: { fp: 0.0, we: 0.0 },
  geothermal: { fp: 0.0, we: 0.0 },
}

const CARRIER_LABELS: Record<string, string> = {
  electricity: "Energia elektryczna",
  natural_gas: "Gaz ziemny",
  lpg: "Gaz płynny LPG",
  heating_oil: "Olej opałowy",
  hard_coal: "Węgiel kamienny",
  lignite: "Węgiel brunatny",
  district_heating: "Ciepło sieciowe",
  biomass: "Biomasa",
  biogas: "Biogaz",
  solar: "Energia słoneczna",
  wind: "Energia wiatru",
  geothermal: "Energia geotermalna",
}

function carrier(value: unknown): string | undefined {
  return typeof value === "string" && value ? value : undefined
}

function carrierLabel(value: string): string {
  return CARRIER_LABELS[value] ?? value
}

export default function PrimaryEnergyFactorsPage() {
  const project = useAppStore((state) => state.project)
  const typedProject = project as ProjectWithPrimaryEnergy | null

  const used = new Set<string>(["electricity"])
  if (project) {
    const heating = project.systems?.heating
    const cooling = project.systems?.cooling
    const dhw = project.systems?.dhw
    if (heating?.system_type !== "none") {
      const value = carrier(heating?.fuel_or_carrier)
      if (value) used.add(value)
    }
    if (cooling && cooling.system_type !== "none") {
      const value = carrier(cooling.fuel_or_carrier)
      if (value) used.add(value)
    }
    if (dhw?.system_type !== "none") {
      const value = carrier(dhw?.fuel_or_carrier)
      if (value) used.add(value)
    }
  }
  const carriers = Array.from(used).sort()

  function updateFactor(carrierName: string, field: keyof Factor, value: number) {
    if (!Number.isFinite(value) || value < 0) return
    useAppStore.setState((state) => {
      if (!state.project) return {}
      const current = state.project as ProjectWithPrimaryEnergy
      const currentFactor = current.primary_energy?.[carrierName]
        ?? FALLBACK_FACTORS[carrierName]
        ?? { fp: 0.0, we: 0.0 }
      return {
        project: {
          ...state.project,
          primary_energy: {
            ...(current.primary_energy ?? {}),
            [carrierName]: { ...currentFactor, [field]: value },
          },
        } as BuildingProject,
      }
    })
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <div className="space-y-3">
        <Button variant="ghost" size="sm" asChild className="-ml-3">
          <Link href="/normative/certificate">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Miesięczne dane formalnej charakterystyki
          </Link>
        </Button>
        <h1 className="text-3xl font-semibold tracking-tight">Współczynniki energii pierwotnej i emisji</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          W tej sekcji ustawiasz wartości liczbowe używane do przeliczenia energii końcowej na
          nieodnawialną energię pierwotną oraz do obliczenia emisji dwutlenku węgla. Dla formalnego
          obliczenia samo wpisanie liczby nie wystarcza — źródło każdej wartości należy zapisać w
          sekcji „Dane źródłowe do formalnego obliczenia”.
        </p>
      </div>

      {!project ? (
        <Alert variant="destructive">
          <AlertTitle>Brak projektu budynku</AlertTitle>
          <AlertDescription>Najpierw utwórz lub wczytaj projekt budynku.</AlertDescription>
        </Alert>
      ) : (
        <Alert>
          <AlertTitle>Nie zmieniaj współczynnika bez udokumentowanej podstawy</AlertTitle>
          <AlertDescription>
            Współczynnik nakładu nieodnawialnej energii pierwotnej wpływa bezpośrednio na wynik Ep.
            Wprowadź wartość właściwą dla danego nośnika i konkretnego przypadku. Jeżeli stosujesz
            wartość udostępnioną przez dostawcę, zapisz jej źródło. Jeżeli stosujesz wartość z tabeli
            metodologii, również opisz to w danych źródłowych.
          </AlertDescription>
        </Alert>
      )}

      {carriers.map((carrierName) => {
        const factor = typedProject?.primary_energy?.[carrierName]
          ?? FALLBACK_FACTORS[carrierName]
          ?? { fp: 0.0, we: 0.0 }
        return (
          <Card key={carrierName}>
            <CardHeader><CardTitle>{carrierLabel(carrierName)}</CardTitle></CardHeader>
            <CardContent className="grid gap-5 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor={`fp-${carrierName}`}>
                  Współczynnik nakładu nieodnawialnej energii pierwotnej (wi) [-]
                </Label>
                <Input
                  id={`fp-${carrierName}`}
                  type="number"
                  step="any"
                  min="0"
                  value={factor.fp}
                  disabled={!project}
                  onChange={(event) => updateFactor(carrierName, "fp", Number(event.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  Ta wartość służy do przeliczenia energii końcowej danego nośnika na
                  nieodnawialną energię pierwotną.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor={`we-${carrierName}`}>Wskaźnik emisji dwutlenku węgla [kg CO₂/kWh]</Label>
                <Input
                  id={`we-${carrierName}`}
                  type="number"
                  step="any"
                  min="0"
                  value={factor.we}
                  disabled={!project}
                  onChange={(event) => updateFactor(carrierName, "we", Number(event.target.value))}
                />
                <p className="text-xs text-muted-foreground">
                  Wartość określa emisję przypisaną do 1 kWh energii końcowej danego nośnika.
                </p>
              </div>
            </CardContent>
          </Card>
        )
      })}
    </main>
  )
}

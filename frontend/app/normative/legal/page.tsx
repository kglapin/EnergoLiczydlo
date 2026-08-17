"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  loadNormativeSettings,
  saveNormativeSettings,
  type NormativeSettings,
} from "@/lib/normative-settings"
import { useAppStore } from "@/lib/store"

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

function carrierValue(value: unknown): string | undefined {
  return typeof value === "string" && value !== "" ? value : undefined
}

function carrierLabel(value: string): string {
  return CARRIER_LABELS[value] ?? value
}

function optionalNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

export default function LegalProvenancePage() {
  const project = useAppStore((state) => state.project)
  const [settings, setSettings] = useState<NormativeSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setSettings(loadNormativeSettings())
  }, [])

  const usedCarriers = useMemo(() => {
    const carriers = new Set<string>()
    if (!project) return ["electricity"]
    const heating = project.systems?.heating
    if (heating && heating.system_type !== "none") {
      const carrier = carrierValue(heating.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    const cooling = project.systems?.cooling
    if (cooling && cooling.system_type !== "none") {
      const carrier = carrierValue(cooling.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    const dhw = project.systems?.dhw
    if (dhw && dhw.system_type !== "none") {
      const carrier = carrierValue(dhw.fuel_or_carrier)
      if (carrier) carriers.add(carrier)
    }
    carriers.add("electricity")
    return Array.from(carriers).sort()
  }, [project])

  const groundElements = useMemo(
    () => project?.opaque_building_elements.filter(
      (element) => element.adjacent_space_type === "ground",
    ) ?? [],
    [project],
  )

  if (!settings) {
    return (
      <main className="mx-auto max-w-4xl px-4 py-12 text-sm text-muted-foreground">
        Ładowanie…
      </main>
    )
  }

  const legal = settings.legal

  function updateLegal(patch: Partial<NormativeSettings["legal"]>) {
    setSettings((current) => current ? {
      ...current,
      legal: { ...current.legal, ...patch },
    } : current)
  }

  function updateDesignGroundTemperature(elementId: string, value?: number) {
    setSettings((current) => current ? {
      ...current,
      design_conditions: {
        ...current.design_conditions,
        ground_adjacent_temperature_by_element_c: {
          ...current.design_conditions.ground_adjacent_temperature_by_element_c,
          ...(value === undefined ? {} : { [elementId]: value }),
        },
      },
    } : current)
  }

  function save() {
    if (!settings) return
    saveNormativeSettings(settings)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  return (
    <main className="mx-auto w-full max-w-4xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <div className="space-y-3">
        <Button variant="ghost" size="sm" asChild className="-ml-3">
          <Link href="/normative">
            <ArrowLeft className="mr-2 h-4 w-4" />
            Zaawansowane ustawienia obliczeniowe
          </Link>
        </Button>
        <h1 className="text-3xl font-semibold tracking-tight">Dane źródłowe do formalnego obliczenia</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          W tej sekcji zapisujesz informacje pozwalające odtworzyć podstawę formalnego obliczenia:
          datę, zastosowaną metodologię, źródło danych klimatycznych oraz źródła współczynników
          użytych do obliczenia nieodnawialnej energii pierwotnej. Samo uzupełnienie tej sekcji nie
          nadaje wynikowi statusu prawnego — dokumentuje jednak, skąd pochodzą użyte dane.
        </p>
      </div>

      <Alert>
        <AlertTitle>Współczynnik nakładu nieodnawialnej energii pierwotnej</AlertTitle>
        <AlertDescription>
          Dla każdego używanego nośnika energii zapisz źródło wartości współczynnika. Jeżeli dla
          konkretnego przypadku stosujesz wartość udostępnioną przez dostawcę, wskaż dokument lub
          informację dostawcy. Jeżeli stosujesz wartość z tabeli metodologii, napisz to wprost.
          Nie wystarczy pozostawić samej liczby bez źródła.
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle>Kontrola kompletności danych formalnych</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <label className="flex cursor-pointer items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-input"
              checked={legal.certificate_mode}
              onChange={(event) => updateLegal({ certificate_mode: event.target.checked })}
            />
            Włącz tryb świadectwa i blokuj obliczenie, gdy brakuje wymaganych danych lub ich źródeł
          </label>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="calculation-date">Data wykonania obliczenia</Label>
              <Input
                id="calculation-date"
                type="date"
                value={legal.calculation_date ?? ""}
                onChange={(event) => updateLegal({
                  calculation_date: event.target.value || undefined,
                })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="methodology-source">Zastosowana metodologia i wersja aktu prawnego</Label>
              <Input
                id="methodology-source"
                value={legal.methodology_source ?? ""}
                onChange={(event) => updateLegal({
                  methodology_source: event.target.value || undefined,
                })}
                placeholder="np. pełne oznaczenie rozporządzenia i stan prawny na dzień obliczenia"
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="climate-source">Źródło danych klimatycznych użytych w świadectwie</Label>
            <Input
              id="climate-source"
              value={legal.climate_data_source ?? ""}
              onChange={(event) => updateLegal({
                climate_data_source: event.target.value || undefined,
              })}
              placeholder="nazwa zbioru, stacja meteorologiczna, wersja lub okres oraz źródło pliku"
            />
            <p className="text-xs text-muted-foreground">
              Sam wybór stacji w projekcie nie dokumentuje pochodzenia danych. Wpisz tutaj dokładne
              źródło zestawu klimatycznego wykorzystanego w formalnym obliczeniu.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="utilization-source">Źródło współczynników wykorzystania zysków i strat</Label>
            <Input
              id="utilization-source"
              value={legal.utilization_factor_source ?? ""}
              onChange={(event) => updateLegal({
                utilization_factor_source: event.target.value || undefined,
              })}
              placeholder="wskazanie normy, arkusza obliczeniowego albo innego zweryfikowanego źródła"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="ventilation-source">Źródło danych i współczynników wentylacyjnych</Label>
            <Input
              id="ventilation-source"
              value={legal.ventilation_factor_source ?? ""}
              onChange={(event) => updateLegal({
                ventilation_factor_source: event.target.value || undefined,
              })}
              placeholder="np. dokumentacja projektu, dane urządzenia lub właściwa procedura normowa"
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Źródła współczynników energii pierwotnej</CardTitle>
        </CardHeader>
        <CardContent className="space-y-5">
          {usedCarriers.map((carrier) => (
            <div className="space-y-2" key={carrier}>
              <Label htmlFor={`wi-source-${carrier}`}>
                {carrierLabel(carrier)} — źródło współczynnika nakładu nieodnawialnej energii pierwotnej
              </Label>
              <Input
                id={`wi-source-${carrier}`}
                value={legal.primary_energy_factor_sources[carrier] ?? ""}
                onChange={(event) => updateLegal({
                  primary_energy_factor_sources: {
                    ...legal.primary_energy_factor_sources,
                    [carrier]: event.target.value,
                  },
                })}
                placeholder="np. dokument dostawcy albo informacja, że zastosowano wartość tabelaryczną z metodologii"
              />
            </div>
          ))}
        </CardContent>
      </Card>

      {settings.design_conditions.enabled && groundElements.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Projektowa temperatura po stronie gruntu</CardTitle>
          </CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm leading-6 text-muted-foreground">
              Przy obliczaniu projektowego obciążenia cieplnego aplikacja nie powinna zastępować
              temperatury gruntu średnią z rocznej analizy godzinowej. Dla każdej przegrody do
              gruntu podaj temperaturę projektową wynikającą z przyjętej procedury projektowej.
            </p>
            {groundElements.map((element) => (
              <div className="space-y-2" key={element.id}>
                <Label htmlFor={`design-ground-${element.id}`}>
                  {element.name} — projektowa temperatura po stronie gruntu [°C]
                </Label>
                <Input
                  id={`design-ground-${element.id}`}
                  type="number"
                  step="any"
                  value={
                    settings.design_conditions.ground_adjacent_temperature_by_element_c[
                      element.id
                    ] ?? ""
                  }
                  onChange={(event) => updateDesignGroundTemperature(
                    element.id,
                    optionalNumber(event.target.value),
                  )}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {legal.certificate_mode ? (
        <Alert>
          <AlertTitle>Co zostanie sprawdzone przed formalnym obliczeniem?</AlertTitle>
          <AlertDescription>
            Aplikacja sprawdzi kompletność danych wymaganych dla zastosowanych elementów projektu.
            Jeżeli budynek ma przegrody do gruntu, wymagane będą odpowiednie dane modelu gruntu.
            Jeżeli wentylacja wykorzystuje odzysk ciepła, wymagane będą dane urządzenia i ich źródło.
            Jeżeli liczysz projektowe obciążenie cieplne, wymagane będą także zweryfikowane warunki
            projektowe. Brak danych zatrzyma obliczenie zamiast tworzyć pozornie formalny wynik.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="flex justify-end">
        <Button onClick={save}>
          <Save className="mr-2 h-4 w-4" />
          Zapisz dane źródłowe
        </Button>
      </div>

      {saved ? (
        <p className="text-right text-sm font-medium text-emerald-700">
          Zapisano. Dane zostaną dołączone do następnego obliczenia.
        </p>
      ) : null}
    </main>
  )
}

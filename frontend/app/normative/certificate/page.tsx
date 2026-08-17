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
  type PolishCertificateMonthlySettings,
} from "@/lib/normative-settings"
import { useAppStore } from "@/lib/store"

const MONTH_NAMES = [
  "styczeń", "luty", "marzec", "kwiecień", "maj", "czerwiec",
  "lipiec", "sierpień", "wrzesień", "październik", "listopad", "grudzień",
]

function parseMonthlySeries(text: string): number[] | null {
  const values = text
    .trim()
    .split(/[;,\s]+/)
    .filter(Boolean)
    .map(Number)
  if (values.length !== 12 || values.some((value) => !Number.isFinite(value))) return null
  return values
}

function formatMonthlySeries(values?: number[]): string {
  return values?.length === 12 ? values.join("; ") : ""
}

function MonthlySeriesField({
  id,
  label,
  description,
  value,
  onChange,
}: {
  id: string
  label: string
  description?: string
  value?: number[]
  onChange: (value: number[]) => void
}) {
  const [text, setText] = useState(() => formatMonthlySeries(value))
  const [valid, setValid] = useState(() => value?.length === 12 || !value?.length)

  useEffect(() => setText(formatMonthlySeries(value)), [value])

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        value={text}
        placeholder={MONTH_NAMES.map(() => "0").join("; ")}
        onChange={(event) => {
          const next = event.target.value
          setText(next)
          const parsed = parseMonthlySeries(next)
          setValid(parsed !== null)
          if (parsed) onChange(parsed)
        }}
      />
      <p className={`text-xs leading-5 ${valid ? "text-muted-foreground" : "font-medium text-destructive"}`}>
        {valid
          ? description ?? "Wpisz dokładnie 12 wartości: od stycznia do grudnia. Rozdziel je średnikami, przecinkami albo spacjami."
          : "Wymagane jest dokładnie 12 poprawnych wartości liczbowych — po jednej dla każdego miesiąca od stycznia do grudnia."}
      </p>
    </div>
  )
}

function updateMap(
  settings: NormativeSettings,
  field: keyof PolishCertificateMonthlySettings,
  key: string,
  value: number[] | number,
): NormativeSettings {
  const certificate = settings.polish_certificate
  const current = certificate[field]
  if (typeof value === "number") {
    const map = typeof current === "object" && current !== null && !Array.isArray(current)
      ? current as Record<string, number>
      : {}
    return {
      ...settings,
      polish_certificate: {
        ...certificate,
        [field]: { ...map, [key]: value },
      },
    }
  }
  const map = typeof current === "object" && current !== null && !Array.isArray(current)
    ? current as Record<string, number[]>
    : {}
  return {
    ...settings,
    polish_certificate: {
      ...certificate,
      [field]: { ...map, [key]: value },
    },
  }
}

export default function PolishCertificateEditorPage() {
  const project = useAppStore((state) => state.project)
  const [settings, setSettings] = useState<NormativeSettings | null>(null)
  const [saved, setSaved] = useState(false)

  useEffect(() => setSettings(loadNormativeSettings()), [])

  const conditionedZones = useMemo(
    () => project?.thermal_zones.filter((zone) =>
      ["heated", "cooled", "heated_and_cooled", "semi_heated"].includes(zone.zone_type),
    ) ?? [],
    [project],
  )
  const transparent = project?.transparent_building_elements ?? []
  const groundElements = project?.opaque_building_elements.filter(
    (element) => element.adjacent_space_type === "ground",
  ) ?? []
  const unheatedElements = project?.opaque_building_elements.filter(
    (element) => element.adjacent_space_type === "unheated_zone",
  ) ?? []

  if (!settings) {
    return <main className="mx-auto max-w-5xl px-4 py-12 text-sm text-muted-foreground">Ładowanie…</main>
  }

  const certificate = settings.polish_certificate
  const ventilationType = project?.ventilation.ventilation_type
  const usesRecovery = ventilationType === "mechanical_with_recovery"
  const usesSupplyExtract = ventilationType === "mechanical" || usesRecovery

  function updateCertificate(patch: Partial<PolishCertificateMonthlySettings>) {
    setSettings((current) => current ? {
      ...current,
      polish_certificate: { ...current.polish_certificate, ...patch },
    } : current)
  }

  function save() {
    if (!settings) return
    saveNormativeSettings(settings)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  return (
    <main className="mx-auto w-full max-w-5xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <div className="space-y-3">
        <Button variant="ghost" size="sm" asChild className="-ml-3">
          <Link href="/normative/legal"><ArrowLeft className="mr-2 h-4 w-4" />Dane źródłowe formalnego obliczenia</Link>
        </Button>
        <h1 className="text-3xl font-semibold tracking-tight">Miesięczne dane do formalnej charakterystyki energetycznej</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          Ten formularz zawiera dane używane przez miesięczny silnik formalnej charakterystyki
          energetycznej. Godzinowa analiza 8760 godzin według modelu opartego na PN-EN ISO 52016-1
          jest wykonywana i przechowywana osobno. Dane w tej sekcji nie są automatycznie pobierane
          z wyniku godzinowego.
        </p>
      </div>

      {!project ? (
        <Alert variant="destructive">
          <AlertTitle>Brak projektu budynku</AlertTitle>
          <AlertDescription>Najpierw utwórz lub wczytaj projekt budynku.</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Dane klimatyczne i włączenie obliczenia formalnego</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <label className="flex items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              checked={certificate.enabled}
              onChange={(event) => updateCertificate({ enabled: event.target.checked })}
            />
            Włącz miesięczny silnik formalnej charakterystyki energetycznej
          </label>
          <label className="flex items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              checked={certificate.official_bip_climate_data}
              onChange={(event) => updateCertificate({ official_bip_climate_data: event.target.checked })}
            />
            Potwierdzam, że dane klimatyczne pochodzą z właściwego oficjalnego źródła w Biuletynie Informacji Publicznej dla wybranej stacji
          </label>
          <MonthlySeriesField
            id="monthly-outdoor"
            label="Średnia temperatura zewnętrzna w każdym miesiącu [°C]"
            value={certificate.monthly_outdoor_temperature_c}
            onChange={(value) => updateCertificate({ monthly_outdoor_temperature_c: value })}
          />
        </CardContent>
      </Card>

      {conditionedZones.map((zone) => {
        const heated = ["heated", "heated_and_cooled", "semi_heated"].includes(zone.zone_type)
        const cooled = ["cooled", "heated_and_cooled"].includes(zone.zone_type)
        return (
          <Card key={zone.id}>
            <CardHeader><CardTitle>Strefa: {zone.name}</CardTitle></CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <Label htmlFor={`qint-${zone.id}`}>Średnia gęstość wewnętrznych zysków ciepła [W/m²]</Label>
                <Input
                  id={`qint-${zone.id}`}
                  type="number"
                  step="any"
                  value={certificate.internal_gain_density_w_m2_by_zone[zone.id] ?? ""}
                  onChange={(event) => {
                    const value = Number(event.target.value)
                    if (Number.isFinite(value) && value >= 0) {
                      setSettings((current) => current
                        ? updateMap(current, "internal_gain_density_w_m2_by_zone", zone.id, value)
                        : current)
                    }
                  }}
                />
                <p className="text-xs text-muted-foreground">
                  Wartość opisuje średnie zyski ciepła od ludzi, oświetlenia i urządzeń przypadające na 1 m² powierzchni strefy.
                </p>
              </div>

              {heated ? (
                <>
                  <MonthlySeriesField
                    id={`tint-h-${zone.id}`}
                    label="Temperatura wewnętrzna przy obliczaniu ogrzewania [°C]"
                    value={certificate.heating_internal_temperature_c_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "heating_internal_temperature_c_by_zone", zone.id, value)
                      : current)}
                  />
                  <MonthlySeriesField
                    id={`eta-h-${zone.id}`}
                    label="Miesięczny współczynnik wykorzystania zysków ciepła przy ogrzewaniu (ηH,gn) [-]"
                    value={certificate.heating_gain_utilization_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "heating_gain_utilization_by_zone", zone.id, value)
                      : current)}
                    description="Wpisz 12 zweryfikowanych wartości od 0 do 1, wyznaczonych zgodnie z właściwą procedurą normową. Współczynnik określa, jaka część zysków ciepła może ograniczyć zapotrzebowanie na ogrzewanie."
                  />
                </>
              ) : null}

              {cooled ? (
                <>
                  <MonthlySeriesField
                    id={`tint-c-${zone.id}`}
                    label="Temperatura wewnętrzna przy obliczaniu chłodzenia [°C]"
                    value={certificate.cooling_internal_temperature_c_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "cooling_internal_temperature_c_by_zone", zone.id, value)
                      : current)}
                  />
                  <MonthlySeriesField
                    id={`eta-c-${zone.id}`}
                    label="Miesięczny współczynnik wykorzystania strat ciepła przy chłodzeniu (ηC,ls) [-]"
                    value={certificate.cooling_loss_utilization_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "cooling_loss_utilization_by_zone", zone.id, value)
                      : current)}
                    description="Wpisz 12 zweryfikowanych wartości od 0 do 1, wyznaczonych zgodnie z właściwą procedurą normową. Współczynnik określa, jaka część strat ciepła może ograniczyć zapotrzebowanie na chłodzenie."
                  />
                </>
              ) : null}

              <MonthlySeriesField
                id={`beta-${zone.id}`}
                label="Miesięczny udział czasu użytkowania strefy (β) [-]"
                value={certificate.beta_by_zone[zone.id]}
                onChange={(value) => setSettings((current) => current
                  ? updateMap(current, "beta_by_zone", zone.id, value)
                  : current)}
                description="Wartość od 0 do 1 określająca udział czasu, w którym strefa jest użytkowana zgodnie z przyjętym profilem."
              />
              {usesRecovery ? (
                <MonthlySeriesField
                  id={`recovery-${zone.id}`}
                  label="Miesięczna skuteczność odzysku ciepła z wentylacji (ηoc) [-]"
                  value={certificate.recovery_effectiveness_by_zone[zone.id]}
                  onChange={(value) => setSettings((current) => current
                    ? updateMap(current, "recovery_effectiveness_by_zone", zone.id, value)
                    : current)}
                  description="Wpisz 12 wartości od 0 do 1 właściwych dla formalnego obliczenia. Nie są one automatycznie kopiowane z godzinowej symulacji rekuperatora."
                />
              ) : null}
              {usesSupplyExtract ? (
                <MonthlySeriesField
                  id={`rn-${zone.id}`}
                  label="Miesięczny współczynnik redukcji strumienia w instalacji nawiewno-wywiewnej (rn) [-]"
                  value={certificate.supply_extract_reduction_by_zone[zone.id]}
                  onChange={(value) => setSettings((current) => current
                    ? updateMap(current, "supply_extract_reduction_by_zone", zone.id, value)
                    : current)}
                  description="Wpisz 12 wartości od 0 do 1. Jeżeli seria nie zostanie podana w sytuacji, w której program dopuszcza wartość metodologiczną, zastosowanie wartości zastępczej zostanie jawnie wskazane w wyniku."
                />
              ) : null}
            </CardContent>
          </Card>
        )
      })}

      {transparent.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>Miesięczne promieniowanie słoneczne dla okien i innych przegród przezroczystych</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm text-muted-foreground">
              Dla każdego okna, drzwi przeszklonych lub świetlika podaj energię promieniowania
              słonecznego padającą na jego płaszczyznę w kolejnych miesiącach.
            </p>
            {transparent.map((element) => (
              <MonthlySeriesField
                key={element.id}
                id={`solar-${element.id}`}
                label={`${element.name} — miesięczne promieniowanie na płaszczyznę [kWh/m²]`}
                value={certificate.solar_irradiation_kwh_m2_by_element[element.id]}
                onChange={(value) => setSettings((current) => current
                  ? updateMap(current, "solar_irradiation_kwh_m2_by_element", element.id, value)
                  : current)}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {groundElements.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>Miesięczne temperatury po stronie gruntu</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm text-muted-foreground">
              Podaj 12 temperatur reprezentujących warunki po stronie gruntu dla każdej przegrody
              uwzględnianej w formalnym obliczeniu.
            </p>
            {groundElements.map((element) => (
              <MonthlySeriesField
                key={element.id}
                id={`ground-monthly-${element.id}`}
                label={`${element.name} — temperatura po stronie gruntu [°C]`}
                value={certificate.ground_adjacent_temperature_c_by_element[element.id]}
                onChange={(value) => setSettings((current) => current
                  ? updateMap(current, "ground_adjacent_temperature_c_by_element", element.id, value)
                  : current)}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {unheatedElements.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>Miesięczne temperatury przestrzeni nieogrzewanych</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            <p className="text-sm text-muted-foreground">
              Dla każdej przegrody graniczącej z przestrzenią nieogrzewaną podaj temperaturę tej
              przestrzeni w kolejnych miesiącach.
            </p>
            {unheatedElements.map((element) => (
              <MonthlySeriesField
                key={element.id}
                id={`unheated-monthly-${element.id}`}
                label={`${element.name} — temperatura przestrzeni sąsiedniej [°C]`}
                value={certificate.unheated_adjacent_temperature_c_by_element[element.id]}
                onChange={(value) => setSettings((current) => current
                  ? updateMap(current, "unheated_adjacent_temperature_c_by_element", element.id, value)
                  : current)}
              />
            ))}
          </CardContent>
        </Card>
      ) : null}

      {settings.heat_recovery.frost_strategy === "preheater" ? (
        <Card>
          <CardHeader><CardTitle>Nagrzewnica wstępna chroniąca wymiennik przed zamarzaniem</CardTitle></CardHeader>
          <CardContent>
            <MonthlySeriesField
              id="preheater-monthly"
              label="Zużycie energii elektrycznej przez nagrzewnicę wstępną [kWh/miesiąc]"
              value={certificate.preheater_electricity_kwh_by_month}
              onChange={(value) => updateCertificate({ preheater_electricity_kwh_by_month: value })}
              description="Podaj 12 miesięcznych wartości właściwych dla formalnych danych świadectwa. Program nie kopiuje automatycznie zużycia obliczonego w godzinowej analizie typowego roku meteorologicznego."
            />
          </CardContent>
        </Card>
      ) : null}

      <Alert>
        <AlertTitle>Ważne: dane formalne i analiza godzinowa są rozdzielone</AlertTitle>
        <AlertDescription>
          Główne wskaźniki formalnego świadectwa są liczone z danych tej sekcji i pozostałych danych
          wymaganych przez metodologię. Godzinowa analiza 8760 godzin pozostaje osobnym wynikiem
          technicznym i może służyć do kontroli oraz porównania zachowania budynku.
        </AlertDescription>
      </Alert>

      <div className="flex justify-end">
        <Button onClick={save}><Save className="mr-2 h-4 w-4" />Zapisz dane miesięczne</Button>
      </div>
      {saved ? <p className="text-right text-sm font-medium text-emerald-700">Zapisano dane miesięczne.</p> : null}
    </main>
  )
}

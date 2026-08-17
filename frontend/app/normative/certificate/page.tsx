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
  "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI", "XII",
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
          ? description ?? "12 wartości od stycznia do grudnia, rozdzielonych średnikiem, przecinkiem lub spacją."
          : "Wymagane jest dokładnie 12 poprawnych wartości liczbowych."}
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
          <Link href="/normative/legal"><ArrowLeft className="mr-2 h-4 w-4" />Tryb formalny</Link>
        </Button>
        <h1 className="text-3xl font-semibold tracking-tight">Dane miesięczne polskiego świadectwa</h1>
        <p className="text-sm leading-6 text-muted-foreground">
          Ten formularz przygotowuje dane dla formalnego silnika miesięcznego. Nie zmienia ani nie
          zastępuje równoległej analizy 8760 h ISO 52016.
        </p>
      </div>

      {!project ? (
        <Alert variant="destructive">
          <AlertTitle>Brak projektu</AlertTitle>
          <AlertDescription>Najpierw utwórz lub wczytaj projekt budynku.</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader><CardTitle>Klimat i aktywacja metody</CardTitle></CardHeader>
        <CardContent className="space-y-5">
          <label className="flex items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              checked={certificate.enabled}
              onChange={(event) => updateCertificate({ enabled: event.target.checked })}
            />
            Włącz miesięczny silnik świadectwa
          </label>
          <label className="flex items-center gap-3 text-sm font-medium">
            <input
              type="checkbox"
              checked={certificate.official_bip_climate_data}
              onChange={(event) => updateCertificate({ official_bip_climate_data: event.target.checked })}
            />
            Dane pochodzą z właściwego ministerialnego BIP dla wybranej stacji
          </label>
          <MonthlySeriesField
            id="monthly-outdoor"
            label="Średnia miesięczna temperatura zewnętrzna [°C]"
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
                <Label htmlFor={`qint-${zone.id}`}>Zyski wewnętrzne qint [W/m²]</Label>
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
              </div>

              {heated ? (
                <>
                  <MonthlySeriesField
                    id={`tint-h-${zone.id}`}
                    label="Temperatura wewnętrzna do ogrzewania [°C]"
                    value={certificate.heating_internal_temperature_c_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "heating_internal_temperature_c_by_zone", zone.id, value)
                      : current)}
                  />
                  <MonthlySeriesField
                    id={`eta-h-${zone.id}`}
                    label="ηH,gn — współczynnik wykorzystania zysków [-]"
                    value={certificate.heating_gain_utilization_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "heating_gain_utilization_by_zone", zone.id, value)
                      : current)}
                    description="12 zweryfikowanych wartości 0–1 wyznaczonych zgodnie z właściwą Polską Normą."
                  />
                </>
              ) : null}

              {cooled ? (
                <>
                  <MonthlySeriesField
                    id={`tint-c-${zone.id}`}
                    label="Temperatura wewnętrzna do chłodzenia [°C]"
                    value={certificate.cooling_internal_temperature_c_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "cooling_internal_temperature_c_by_zone", zone.id, value)
                      : current)}
                  />
                  <MonthlySeriesField
                    id={`eta-c-${zone.id}`}
                    label="ηC,ls — współczynnik wykorzystania strat [-]"
                    value={certificate.cooling_loss_utilization_by_zone[zone.id]}
                    onChange={(value) => setSettings((current) => current
                      ? updateMap(current, "cooling_loss_utilization_by_zone", zone.id, value)
                      : current)}
                    description="12 zweryfikowanych wartości 0–1 wyznaczonych zgodnie z właściwą Polską Normą."
                  />
                </>
              ) : null}

              <MonthlySeriesField
                id={`beta-${zone.id}`}
                label="β — udział czasu użytkowania [-]"
                value={certificate.beta_by_zone[zone.id]}
                onChange={(value) => setSettings((current) => current
                  ? updateMap(current, "beta_by_zone", zone.id, value)
                  : current)}
              />
              {usesRecovery ? (
                <MonthlySeriesField
                  id={`recovery-${zone.id}`}
                  label="ηoc — miesięczna skuteczność odzysku ciepła [-]"
                  value={certificate.recovery_effectiveness_by_zone[zone.id]}
                  onChange={(value) => setSettings((current) => current
                    ? updateMap(current, "recovery_effectiveness_by_zone", zone.id, value)
                    : current)}
                />
              ) : null}
              {usesSupplyExtract ? (
                <MonthlySeriesField
                  id={`rn-${zone.id}`}
                  label="rn — redukcja strumienia nawiewno-wywiewnego [-]"
                  value={certificate.supply_extract_reduction_by_zone[zone.id]}
                  onChange={(value) => setSettings((current) => current
                    ? updateMap(current, "supply_extract_reduction_by_zone", zone.id, value)
                    : current)}
                  description="Jeżeli seria pozostanie pusta i używany jest strumień normatywny, backend raportuje fallback rn=0,75."
                />
              ) : null}
            </CardContent>
          </Card>
        )
      })}

      {transparent.length > 0 ? (
        <Card>
          <CardHeader><CardTitle>Promieniowanie przez przegrody przezroczyste</CardTitle></CardHeader>
          <CardContent className="space-y-5">
            {transparent.map((element) => (
              <MonthlySeriesField
                key={element.id}
                id={`solar-${element.id}`}
                label={`${element.name} — promieniowanie miesięczne na płaszczyznę [kWh/m²]`}
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
          <CardHeader><CardTitle>Miesięczne warunki dla gruntu</CardTitle></CardHeader>
          <CardContent className="space-y-5">
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
          <CardHeader><CardTitle>Przestrzenie nieogrzewane</CardTitle></CardHeader>
          <CardContent className="space-y-5">
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
          <CardHeader><CardTitle>Nagrzewnica przeciwzamrożeniowa</CardTitle></CardHeader>
          <CardContent>
            <MonthlySeriesField
              id="preheater-monthly"
              label="Energia elektryczna nagrzewnicy [kWh/mies.]"
              value={certificate.preheater_electricity_kwh_by_month}
              onChange={(value) => updateCertificate({ preheater_electricity_kwh_by_month: value })}
              description="Formalny wynik nie kopiuje tej energii z TMY — podaj 12 wartości właściwych dla danych świadectwa."
            />
          </CardContent>
        </Card>
      ) : null}

      <div className="flex justify-end">
        <Button onClick={save}><Save className="mr-2 h-4 w-4" />Zapisz dane miesięczne</Button>
      </div>
      {saved ? <p className="text-right text-sm font-medium text-emerald-700">Zapisano.</p> : null}
    </main>
  )
}

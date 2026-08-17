"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save, RotateCcw } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  clearNormativeSettings,
  defaultNormativeSettings,
  loadNormativeSettings,
  saveNormativeSettings,
  type GroundElementSettings,
  type NormativeSettings,
} from "@/lib/normative-settings"
import { useAppStore } from "@/lib/store"

function cloneDefaults(): NormativeSettings {
  return JSON.parse(JSON.stringify(defaultNormativeSettings)) as NormativeSettings
}

function optionalNumber(value: string): number | undefined {
  if (value.trim() === "") return undefined
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : undefined
}

function NumberField({
  id,
  label,
  value,
  onChange,
  step = "any",
  min,
  max,
  hint,
}: {
  id: string
  label: string
  value?: number
  onChange: (value: number | undefined) => void
  step?: string
  min?: number
  max?: number
  hint?: string
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type="number"
        step={step}
        min={min}
        max={max}
        value={value ?? ""}
        onChange={(event) => onChange(optionalNumber(event.target.value))}
      />
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  )
}

function Toggle({
  id,
  label,
  checked,
  onChange,
}: {
  id: string
  label: string
  checked: boolean
  onChange: (checked: boolean) => void
}) {
  return (
    <label htmlFor={id} className="flex cursor-pointer items-center gap-3 text-sm font-medium">
      <input
        id={id}
        type="checkbox"
        className="h-4 w-4 rounded border-input"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  )
}

function JsonField({
  id,
  label,
  value,
  onChange,
  hint,
}: {
  id: string
  label: string
  value: unknown
  onChange: (value: unknown) => void
  hint?: string
}) {
  const [text, setText] = useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setText(JSON.stringify(value, null, 2))
  }, [value])

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <textarea
        id={id}
        className="min-h-32 w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm shadow-sm outline-none focus-visible:ring-1 focus-visible:ring-ring"
        value={text}
        onChange={(event) => {
          const next = event.target.value
          setText(next)
          try {
            const parsed = JSON.parse(next) as unknown
            onChange(parsed)
            setError(null)
          } catch {
            setError("Nieprawidłowy zapis danych w formacie JSON — ta wartość nie zostanie użyta w obliczeniu.")
          }
        }}
      />
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
      {error ? <p className="text-xs font-medium text-destructive">{error}</p> : null}
    </div>
  )
}

export default function NormativeSettingsPage() {
  const project = useAppStore((state) => state.project)
  const [settings, setSettings] = useState<NormativeSettings>(cloneDefaults)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    setSettings(loadNormativeSettings())
  }, [])

  const groundElements = useMemo(
    () => project?.opaque_building_elements.filter(
      (element) => element.adjacent_space_type === "ground" || element.element_type === "ground_floor",
    ) ?? [],
    [project],
  )
  const conditionedZones = useMemo(
    () => project?.thermal_zones.filter((zone) => zone.zone_type !== "unheated") ?? [],
    [project],
  )
  const unheatedBoundaries = useMemo(
    () => project?.opaque_building_elements.filter(
      (element) => element.adjacent_space_type === "unheated_zone",
    ) ?? [],
    [project],
  )

  function updateGroundElement(id: string, patch: Partial<GroundElementSettings>) {
    setSettings((current) => ({
      ...current,
      ground: {
        ...current.ground,
        elements: {
          ...current.ground.elements,
          [id]: {
            ...(current.ground.elements[id] ?? {}),
            ...patch,
          },
        },
      },
    }))
  }

  function save() {
    saveNormativeSettings(settings)
    setSaved(true)
    window.setTimeout(() => setSaved(false), 2500)
  }

  function reset() {
    clearNormativeSettings()
    setSettings(cloneDefaults())
    setSaved(false)
  }

  return (
    <main className="mx-auto w-full max-w-6xl space-y-8 px-4 py-8 md:px-8 md:py-12">
      <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <Button variant="ghost" size="sm" asChild className="-ml-3">
            <Link href="/building"><ArrowLeft className="mr-2 h-4 w-4" />Wróć do budynku</Link>
          </Button>
          <h1 className="text-3xl font-semibold tracking-tight">Zaawansowane ustawienia obliczeniowe</h1>
          <p className="max-w-3xl text-sm text-muted-foreground">
            Tutaj ustawiasz szczegółowy model wymiany ciepła z gruntem, pracę wentylacji z odzyskiem
            ciepła oraz projektowe obciążenie cieplne. Jeżeli włączysz tryb wymagający formalnej
            kontroli danych, aplikacja nie będzie zgadywać brakujących wartości — muszą one pochodzić
            z dokumentacji projektu, właściwej procedury normowej albo dokumentacji urządzenia.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={reset}><RotateCcw className="mr-2 h-4 w-4" />Przywróć wartości początkowe</Button>
          <Button onClick={save}><Save className="mr-2 h-4 w-4" />Zapisz ustawienia</Button>
        </div>
      </div>

      {saved ? (
        <Alert>
          <AlertTitle>Zapisano ustawienia</AlertTitle>
          <AlertDescription>
            Te dane zostaną automatycznie dołączone do następnego obliczenia.
          </AlertDescription>
        </Alert>
      ) : null}

      {!project ? (
        <Alert>
          <AlertTitle>Brak aktywnego projektu budynku</AlertTitle>
          <AlertDescription>
            Możesz ustawić parametry ogólne, ale ustawienia konkretnych przegród i stref będą dostępne
            po utworzeniu albo wczytaniu projektu budynku.
          </AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>1. Wymiana ciepła z gruntem — PN-EN ISO 13370</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <Toggle
              id="ground-enabled"
              label="Włącz rozszerzony model wymiany ciepła z gruntem"
              checked={settings.ground.enabled}
              onChange={(enabled) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, enabled },
              }))}
            />
            <Toggle
              id="ground-certificate"
              label="Wymagaj zweryfikowanych danych zamiast wartości diagnostycznych"
              checked={settings.ground.certificate_mode}
              onChange={(certificate_mode) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, certificate_mode },
              }))}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <NumberField
              id="soil-lambda"
              label="Przewodność cieplna gruntu [W/(m·K)]"
              value={settings.ground.soil_conductivity_w_mk}
              onChange={(soil_conductivity_w_mk) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, soil_conductivity_w_mk },
              }))}
              min={0}
            />
            <NumberField
              id="soil-density"
              label="Gęstość gruntu [kg/m³]"
              value={settings.ground.soil_density_kg_m3}
              onChange={(soil_density_kg_m3) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, soil_density_kg_m3 },
              }))}
              min={0}
            />
            <NumberField
              id="soil-cp"
              label="Ciepło właściwe gruntu [J/(kg·K)]"
              value={settings.ground.soil_specific_heat_j_kgk}
              onChange={(soil_specific_heat_j_kgk) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, soil_specific_heat_j_kgk },
              }))}
              min={0}
            />
            <NumberField
              id="wall-thickness"
              label="Grubość ściany zewnętrznej [m]"
              value={settings.ground.external_wall_thickness_m}
              onChange={(external_wall_thickness_m) => setSettings((current) => ({
                ...current,
                ground: { ...current.ground, external_wall_thickness_m },
              }))}
              min={0}
            />
          </div>

          <Alert>
            <AlertTitle>Zmiana temperatury gruntu w ciągu roku</AlertTitle>
            <AlertDescription>
              Przy analizie godzinowej każda przegroda do gruntu może wymagać współczynnika określającego,
              jak mocno roczna zmiana temperatury jest tłumiona w gruncie, oraz przesunięcia czasowego tej
              odpowiedzi. W trybie wymagającym zweryfikowanych danych wartości te muszą pochodzić z właściwej
              procedury obliczeniowej. Program nie tworzy ich z arbitralnych stałych.
            </AlertDescription>
          </Alert>

          <div className="space-y-4">
            {groundElements.length === 0 ? (
              <p className="text-sm text-muted-foreground">W aktywnym projekcie nie ma przegród stykających się z gruntem.</p>
            ) : groundElements.map((element) => {
              const config = settings.ground.elements[element.id] ?? {}
              return (
                <div key={element.id} className="rounded-lg border p-4">
                  <div className="mb-4">
                    <p className="font-medium">{element.name}</p>
                    <p className="text-xs text-muted-foreground">Identyfikator techniczny: {element.id}</p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    <NumberField
                      id={`${element.id}-perimeter`}
                      label="Obwód podłogi wystawiony na wymianę z gruntem [m]"
                      value={config.exposed_perimeter_m}
                      onChange={(exposed_perimeter_m) => updateGroundElement(
                        element.id, { exposed_perimeter_m },
                      )}
                      min={0}
                    />
                    <NumberField
                      id={`${element.id}-rf`}
                      label="Opór cieplny warstw podłogi [m²·K/W]"
                      value={config.floor_thermal_resistance_m2k_w}
                      onChange={(floor_thermal_resistance_m2k_w) => updateGroundElement(
                        element.id, { floor_thermal_resistance_m2k_w },
                      )}
                      min={0}
                    />
                    <NumberField
                      id={`${element.id}-depth`}
                      label="Głębokość piwnicy lub położenia elementu poniżej terenu [m]"
                      value={config.basement_depth_m}
                      onChange={(basement_depth_m) => updateGroundElement(
                        element.id, { basement_depth_m },
                      )}
                      min={0}
                    />
                    <NumberField
                      id={`${element.id}-ratio`}
                      label="Współczynnik tłumienia rocznej zmiany temperatury [-]"
                      value={config.periodic_amplitude_ratio}
                      onChange={(periodic_amplitude_ratio) => updateGroundElement(
                        element.id, { periodic_amplitude_ratio },
                      )}
                      min={0}
                      max={1}
                      hint="0 oznacza pełne wytłumienie zmiany temperatury, a 1 brak tłumienia. Wartość formalna musi pochodzić ze zweryfikowanej procedury."
                    />
                    <NumberField
                      id={`${element.id}-phase`}
                      label="Przesunięcie czasowe odpowiedzi gruntu [dni]"
                      value={config.phase_shift_days}
                      onChange={(phase_shift_days) => updateGroundElement(
                        element.id, { phase_shift_days },
                      )}
                      min={0}
                      max={365}
                    />
                    <NumberField
                      id={`${element.id}-diagnostic-depth`}
                      label="Efektywna głębokość używana tylko w analizie diagnostycznej [m]"
                      value={config.diagnostic_effective_depth_m}
                      onChange={(diagnostic_effective_depth_m) => updateGroundElement(
                        element.id, { diagnostic_effective_depth_m },
                      )}
                      min={0}
                      hint="To pole nie jest używane jako formalna wartość normowa."
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>2. Wentylacja z odzyskiem ciepła — praca wymiennika i ochrona przed zamarzaniem</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <Toggle
              id="hr-enabled"
              label="Włącz szczegółowy godzinowy model odzysku ciepła"
              checked={settings.heat_recovery.enabled}
              onChange={(enabled) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, enabled },
              }))}
            />
            <Toggle
              id="hr-certificate"
              label="Wymagaj źródła charakterystyki zastosowanego urządzenia"
              checked={settings.heat_recovery.certificate_mode}
              onChange={(certificate_mode) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, certificate_mode },
              }))}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="performance-source">Źródło danych dotyczących sprawności urządzenia</Label>
            <Input
              id="performance-source"
              value={settings.heat_recovery.performance_source ?? ""}
              onChange={(event) => setSettings((current) => ({
                ...current,
                heat_recovery: {
                  ...current.heat_recovery,
                  performance_source: event.target.value || undefined,
                },
              }))}
              placeholder="np. karta producenta albo raport z badania wraz z numerem dokumentu"
            />
          </div>

          <JsonField
            id="efficiency-curve"
            label="Sprawność odzysku ciepła dla różnych temperatur zewnętrznych"
            value={settings.heat_recovery.efficiency_curve}
            onChange={(value) => setSettings((current) => ({
              ...current,
              heat_recovery: {
                ...current.heat_recovery,
                efficiency_curve: Array.isArray(value)
                  ? value as NormativeSettings["heat_recovery"]["efficiency_curve"]
                  : [],
              },
            }))}
            hint='Dane techniczne zapisuje się jako listę punktów, np. [{"outdoor_temperature_c": -10, "efficiency": 0.82}]. Pierwsza liczba oznacza temperaturę zewnętrzną w °C, a druga sprawność od 0 do 1. Pusta lista oznacza użycie sprawności wpisanej w głównych danych projektu.'
          />

          <div className="grid gap-4 md:grid-cols-2">
            <Toggle
              id="bypass-enabled"
              label="Włącz letnie obejście wymiennika odzysku ciepła"
              checked={settings.heat_recovery.summer_bypass_enabled}
              onChange={(summer_bypass_enabled) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, summer_bypass_enabled },
              }))}
            />
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            <NumberField
              id="bypass-min"
              label="Najniższa temperatura zewnętrzna pozwalająca włączyć obejście [°C]"
              value={settings.heat_recovery.bypass_min_outdoor_c}
              onChange={(bypass_min_outdoor_c) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, bypass_min_outdoor_c },
              }))}
            />
            <NumberField
              id="bypass-max"
              label="Najwyższa temperatura zewnętrzna pozwalająca włączyć obejście [°C]"
              value={settings.heat_recovery.bypass_max_outdoor_c}
              onChange={(bypass_max_outdoor_c) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, bypass_max_outdoor_c },
              }))}
            />
            <NumberField
              id="bypass-margin"
              label="Wymagana różnica względem zadanej temperatury chłodzenia [K]"
              value={settings.heat_recovery.bypass_indoor_margin_k}
              onChange={(bypass_indoor_margin_k) => setSettings((current) => ({
                ...current,
                heat_recovery: {
                  ...current.heat_recovery,
                  bypass_indoor_margin_k: bypass_indoor_margin_k ?? 1,
                },
              }))}
              min={0}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div className="space-y-2">
              <Label htmlFor="frost-strategy">Sposób ochrony wymiennika przed zamarzaniem</Label>
              <select
                id="frost-strategy"
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
                value={settings.heat_recovery.frost_strategy}
                onChange={(event) => setSettings((current) => ({
                  ...current,
                  heat_recovery: {
                    ...current.heat_recovery,
                    frost_strategy: event.target.value as NormativeSettings["heat_recovery"]["frost_strategy"],
                  },
                }))}
              >
                <option value="none">Brak aktywnej ochrony</option>
                <option value="preheater">Nagrzewnica wstępna</option>
                <option value="reduce_recovery">Ograniczenie odzysku ciepła</option>
                <option value="disable_recovery">Czasowe wyłączenie odzysku ciepła</option>
              </select>
            </div>
            <NumberField
              id="frost-limit"
              label="Minimalna dopuszczalna temperatura powietrza wyrzucanego [°C]"
              value={settings.heat_recovery.frost_exhaust_limit_c}
              onChange={(frost_exhaust_limit_c) => setSettings((current) => ({
                ...current,
                heat_recovery: {
                  ...current.heat_recovery,
                  frost_exhaust_limit_c: frost_exhaust_limit_c ?? 0,
                },
              }))}
            />
            <NumberField
              id="indoor-rh"
              label="Wilgotność względna powietrza usuwanego [-]"
              value={settings.heat_recovery.indoor_relative_humidity}
              onChange={(indoor_relative_humidity) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, indoor_relative_humidity },
              }))}
              min={0}
              max={1}
              hint="Wpisz np. 0,50 dla 50% wilgotności względnej. Wymagana przy formalnej kontroli aktywnej ochrony przed zamarzaniem."
            />
            <NumberField
              id="preheater-power"
              label="Maksymalna moc elektryczna nagrzewnicy wstępnej [W]"
              value={settings.heat_recovery.preheater_max_power_w}
              onChange={(preheater_max_power_w) => setSettings((current) => ({
                ...current,
                heat_recovery: { ...current.heat_recovery, preheater_max_power_w },
              }))}
              min={0}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>3. Projektowe obciążenie cieplne</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-4 md:grid-cols-2">
            <Toggle
              id="design-enabled"
              label="Oblicz projektowe obciążenie cieplne niezależnie od typowego roku meteorologicznego (TMY)"
              checked={settings.design_conditions.enabled}
              onChange={(enabled) => setSettings((current) => ({
                ...current,
                design_conditions: { ...current.design_conditions, enabled },
              }))}
            />
            <Toggle
              id="design-certificate"
              label="Wymagaj udokumentowanego źródła projektowej temperatury zewnętrznej"
              checked={settings.design_conditions.certificate_mode}
              onChange={(certificate_mode) => setSettings((current) => ({
                ...current,
                design_conditions: { ...current.design_conditions, certificate_mode },
              }))}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <NumberField
              id="design-outdoor"
              label="Projektowa temperatura zewnętrzna [°C]"
              value={settings.design_conditions.outdoor_design_temperature_c}
              onChange={(outdoor_design_temperature_c) => setSettings((current) => ({
                ...current,
                design_conditions: { ...current.design_conditions, outdoor_design_temperature_c },
              }))}
              hint="Podaj temperaturę wynikającą z właściwego źródła projektowego. Nie należy zastępować jej najniższą temperaturą występującą w typowym roku meteorologicznym."
            />
            <div className="space-y-2">
              <Label htmlFor="design-source">Źródło projektowej temperatury zewnętrznej</Label>
              <Input
                id="design-source"
                value={settings.design_conditions.source ?? ""}
                onChange={(event) => setSettings((current) => ({
                  ...current,
                  design_conditions: {
                    ...current.design_conditions,
                    source: event.target.value || undefined,
                  },
                }))}
                placeholder="np. właściwy dokument projektowy lub załącznik krajowy wraz z lokalizacją"
              />
            </div>
          </div>

          <div className="space-y-4">
            <h3 className="font-medium">Dodatkowa moc potrzebna do ponownego nagrzania pomieszczeń</h3>
            <p className="text-sm text-muted-foreground">
              To pole służy wyłącznie do projektowego obciążenia cieplnego. Nie jest automatycznie
              dodawane do rocznego zużycia energii.
            </p>
            {conditionedZones.length === 0 ? (
              <p className="text-sm text-muted-foreground">Brak aktywnych stref.</p>
            ) : conditionedZones.map((zone) => (
              <NumberField
                key={zone.id}
                id={`heatup-${zone.id}`}
                label={`${zone.name} — dodatkowa moc ponownego nagrzania [W]`}
                value={settings.design_conditions.heat_up_power_by_zone_w[zone.id]}
                onChange={(value) => setSettings((current) => ({
                  ...current,
                  design_conditions: {
                    ...current.design_conditions,
                    heat_up_power_by_zone_w: {
                      ...current.design_conditions.heat_up_power_by_zone_w,
                      [zone.id]: value ?? 0,
                    },
                  },
                }))}
                min={0}
              />
            ))}
          </div>

          {unheatedBoundaries.length > 0 ? (
            <div className="space-y-4">
              <h3 className="font-medium">Projektowe temperatury przestrzeni nieogrzewanych</h3>
              <p className="text-sm text-muted-foreground">
                Przy formalnej kontroli obciążenia projektowego program nie przyjmuje automatycznie
                wartości „temperatura zewnętrzna + 3 K”. Temperaturę po drugiej stronie przegrody
                należy podać na podstawie właściwych danych projektowych.
              </p>
              {unheatedBoundaries.map((element) => (
                <NumberField
                  key={element.id}
                  id={`unheated-${element.id}`}
                  label={`${element.name} — projektowa temperatura po drugiej stronie przegrody [°C]`}
                  value={settings.design_conditions.unheated_adjacent_temperature_by_element_c[element.id]}
                  onChange={(value) => setSettings((current) => ({
                    ...current,
                    design_conditions: {
                      ...current.design_conditions,
                      unheated_adjacent_temperature_by_element_c: {
                        ...current.design_conditions.unheated_adjacent_temperature_by_element_c,
                        ...(value === undefined ? {} : { [element.id]: value }),
                      },
                    },
                  }))}
                />
              ))}
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Alert>
        <AlertTitle>Jak interpretować wyniki?</AlertTitle>
        <AlertDescription>
          Projektowe obciążenie cieplne jest osobnym wynikiem mocy i nie zwiększa rocznej energii
          użytkowej. Godzinowa analiza 8760 godzin jest analizą techniczną. Jeżeli włączony jest tryb
          świadectwa, główne formalne wartości energii użytkowej (Eu), energii końcowej (Ek) i
          nieodnawialnej energii pierwotnej (Ep) pochodzą z osobnego miesięcznego silnika formalnej
          charakterystyki energetycznej. Energia elektryczna zużywana przez aktywną nagrzewnicę
          wstępną jest energią systemową i może zwiększać Ek oraz Ep.
        </AlertDescription>
      </Alert>
    </main>
  )
}

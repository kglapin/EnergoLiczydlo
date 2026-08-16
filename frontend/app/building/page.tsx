"use client"

import { useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { useForm, useFieldArray, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormField } from "@/components/form-field"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { calculate, fetchStations } from "@/lib/api"
import { useAppStore } from "@/lib/store"

const zoneSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  zone_type: z.string(),
  floor_area: z.coerce.number().positive(),
  volume: z.coerce.number().positive(),
  setpoint_heating: z.coerce.number(),
  setpoint_cooling: z.coerce.number().optional(),
  occupancy_density: z.coerce.number().min(0),
})

const opaqueSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  zone_id: z.string().min(1),
  element_type: z.string(),
  orientation_azimuth: z.coerce.number(),
  inclination: z.coerce.number(),
  area: z.coerce.number().positive(),
  u_value: z.coerce.number().positive(),
  solar_absorptance: z.coerce.number().min(0).max(1).optional(),
  solar_reduction_factor: z.coerce.number().min(0).max(1).optional(),
  adjacent_space_type: z.string().optional(),
})

const transparentSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  zone_id: z.string().min(1),
  element_type: z.string(),
  orientation_azimuth: z.coerce.number(),
  inclination: z.coerce.number(),
  area: z.coerce.number().positive(),
  u_value: z.coerce.number().positive(),
  g_value: z.coerce.number().min(0).max(1),
  frame_factor: z.coerce.number().min(0).max(1).optional(),
  shading_factor: z.coerce.number().min(0).max(1).optional(),
})

const formSchema = z.object({
  project_name: z.string().min(1),
  general: z.object({
    building_name: z.string().min(1),
    building_type: z.string(),
    construction_year: z.coerce.number(),
    conditioned_floor_area: z.coerce.number().positive(),
    usable_floor_area: z.coerce.number().positive(),
    heated_volume: z.coerce.number().positive(),
    number_of_storeys: z.coerce.number().int().positive(),
  }),
  climate_station_id: z.string().min(1),
  thermal_zones: z.array(zoneSchema).min(1),
  opaque_building_elements: z.array(opaqueSchema).min(1),
  transparent_building_elements: z.array(transparentSchema),
  ventilation: z.object({
    ventilation_type: z.string(),
    airflow_rate: z.coerce.number().min(0),
    heat_recovery_efficiency: z.coerce.number().min(0).max(1),
    infiltration_rate: z.coerce.number().min(0),
  }),
  systems: z.record(z.unknown()).optional(),
})

type FormValues = z.infer<typeof formSchema>

const defaultValues: FormValues = {
  project_name: "Mój budynek",
  general: {
    building_name: "Dom jednorodzinny",
    building_type: "residential",
    construction_year: 2020,
    conditioned_floor_area: 150,
    usable_floor_area: 150,
    heated_volume: 375,
    number_of_storeys: 1,
  },
  climate_station_id: "POL_MZ_Okecie-Warszawa-Chopina.Intl.AP.123750_TMYx.2009-2023",
  thermal_zones: [
    {
      id: "z1",
      name: "Strefa 1",
      zone_type: "heated",
      floor_area: 150,
      volume: 375,
      setpoint_heating: 20,
      setpoint_cooling: 26,
      occupancy_density: 0.03,
    },
  ],
  opaque_building_elements: [
    {
      id: "wall_n",
      name: "Ściana północna",
      zone_id: "z1",
      element_type: "external_wall",
      orientation_azimuth: 0,
      inclination: 90,
      area: 40,
      u_value: 0.25,
      solar_absorptance: 0.6,
      solar_reduction_factor: 0.08,
      adjacent_space_type: "outdoor",
    },
    {
      id: "wall_s",
      name: "Ściana południowa",
      zone_id: "z1",
      element_type: "external_wall",
      orientation_azimuth: 180,
      inclination: 90,
      area: 40,
      u_value: 0.25,
      solar_absorptance: 0.6,
      solar_reduction_factor: 0.08,
      adjacent_space_type: "outdoor",
    },
    {
      id: "roof",
      name: "Dach",
      zone_id: "z1",
      element_type: "roof",
      orientation_azimuth: 0,
      inclination: 0,
      area: 90,
      u_value: 0.18,
      solar_absorptance: 0.6,
      solar_reduction_factor: 0.08,
      adjacent_space_type: "outdoor",
    },
    {
      id: "floor",
      name: "Podłoga na gruncie",
      zone_id: "z1",
      element_type: "ground_floor",
      orientation_azimuth: 0,
      inclination: 180,
      area: 90,
      u_value: 0.25,
      solar_absorptance: 0.6,
      solar_reduction_factor: 0.08,
      adjacent_space_type: "ground",
    },
  ],
  transparent_building_elements: [
    {
      id: "win_s",
      name: "Okno południowe",
      zone_id: "z1",
      element_type: "window",
      orientation_azimuth: 180,
      inclination: 90,
      area: 10,
      u_value: 1.0,
      g_value: 0.6,
      shading_factor: 0.7,
      frame_factor: 0.2,
    },
  ],
  ventilation: {
    ventilation_type: "natural",
    airflow_rate: 120,
    heat_recovery_efficiency: 0,
    infiltration_rate: 0.5,
  },
  systems: {
    heating: {
      system_type: "heat_pump_air",
      fuel_or_carrier: "electricity",
      nominal_power: 10,
      efficiency_or_cop_map: { constant: true, value: 3.5 },
      sink_temperature: 35,
      distribution_loss_factor: 0.95,
    },
    dhw: {
      system_type: "electric_storage",
      daily_demand_per_person: 50,
      target_temperature: 55,
      cold_water_temperature: 10,
      efficiency: 0.9,
    },
  },
}

export default function BuildingFormPage() {
  const router = useRouter()
  const { setProject, setResult } = useAppStore()
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  })

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [stations, setStations] = useState<{ id: string; name: string }[]>([])
  const [stationLoading, setStationLoading] = useState(true)

  useEffect(() => {
    fetchStations()
      .then(setStations)
      .catch(() => setError("Nie udało się pobrać stacji klimatycznych"))
      .finally(() => setStationLoading(false))
  }, [])

  function handleExport() {
    const values = form.getValues()
    const blob = new Blob([JSON.stringify(values, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `${values.project_name || "project"}.json`
    a.click()
    URL.revokeObjectURL(url)
  }

  function handleImport(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => {
      try {
        const parsed = JSON.parse(e.target?.result as string)
        form.reset(parsed)
      } catch (err) {
        setError("Nieprawidłowy plik JSON")
      }
    }
    reader.readAsText(file)
    event.target.value = ""
  }

  const zonesFieldArray = useFieldArray({ control: form.control, name: "thermal_zones" })
  const opaqueFieldArray = useFieldArray({ control: form.control, name: "opaque_building_elements" })
  const transparentFieldArray = useFieldArray({
    control: form.control,
    name: "transparent_building_elements",
  })

  async function onSubmit(values: FormValues) {
    setError(null)
    setLoading(true)
    try {
      const project = {
        version: "0.1.0",
        metadata: {},
        thermal_bridges: { auto_calculate: false, linear_bridges: [], point_bridges: [] },
        internal_gains: {
          occupancy: { power_density: 80 },
          lighting: { power_density: 10 },
          equipment: { power_density: 5 },
        },
        primary_energy: {
          electricity: { fp: 2.5, we: 0.6 },
          natural_gas: { fp: 1.1, we: 0.2 },
          district_heating: { fp: 1.2, we: 0.25 },
          biomass: { fp: 1.0, we: 0.05 },
          renewable: { fp: 1.0, we: 0.0 },
        },
        ...values,
      }
      setProject(project as any)
      const result = await calculate(project as any)
      setResult(result)
      router.push("/results")
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }

  const inputClass = "max-w-sm"

  return (
    <main className="container mx-auto py-8 px-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <h1 className="text-3xl font-bold">Nowa analiza energetyczna</h1>
        <div className="flex gap-2">
          <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()}>
            Wczytaj JSON
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/json"
            className="hidden"
            onChange={handleImport}
          />
          <Button type="button" variant="outline" onClick={handleExport}>
            Zapisz JSON
          </Button>
        </div>
      </div>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <Accordion type="multiple" defaultValue={["general"]} className="space-y-4">
          <AccordionItem value="general">
            <AccordionTrigger>Informacje ogólne</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Wprowadź podstawowe dane budynku. Większość pól posiada ikonę „?”
                z wyjaśnieniem. Wszystkie wymiary i objętości muszą być podane w
                jednostkach metrycznych.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField label="Nazwa projektu" tooltip="Nazwa własna analizy – służy do identyfikacji wyników i plików JSON.">
                  <Input id="project_name" {...form.register("project_name")} className={inputClass} />
                </FormField>
                <FormField label="Nazwa budynku" tooltip="Pełna nazwa obiektu, np. „Budynek biurowy ABC”.">
                  <Input id="building_name" {...form.register("general.building_name")} className={inputClass} />
                </FormField>
                <FormField label="Typ budynku" tooltip="Kategoria budynku używana do profilów wewnętrznych: residential, office, commercial, public.">
                  <Input id="building_type" {...form.register("general.building_type")} className={inputClass} />
                </FormField>
                <FormField label="Rok budowy" tooltip="Rok ukończenia budowy – wpływa na domyślne założenia normowe.">
                  <Input id="construction_year" type="number" {...form.register("general.construction_year")} className={inputClass} />
                </FormField>
                <FormField label="Powierzchnia ogrzewana (m²)" tooltip="Suma powierzchni podłóg we wszystkich strefach ogrzewanych. To mianownik do obliczenia EU/EK/EP.">
                  <Input id="conditioned_floor_area" type="number" step="0.1" placeholder="np. 150" {...form.register("general.conditioned_floor_area")} className={inputClass} />
                </FormField>
                <FormField label="Powierzchnia użytkowa (m²)" tooltip="Powierzchnia użytkowa wg polskiej metodologii (Pu).">
                  <Input id="usable_floor_area" type="number" step="0.1" placeholder="np. 150" {...form.register("general.usable_floor_area")} className={inputClass} />
                </FormField>
                <FormField label="Kubatura ogrzewana (m³)" tooltip="Objętość powietrza we wszystkich ogrzewanych strefach, potrzebna do obliczeń wentylacji.">
                  <Input id="heated_volume" type="number" step="0.1" placeholder="np. 375" {...form.register("general.heated_volume")} className={inputClass} />
                </FormField>
                <FormField label="Liczba kondygnacji" tooltip="Liczba pełnych kondygnacji nadziemnych.">
                  <Input id="number_of_storeys" type="number" {...form.register("general.number_of_storeys")} className={inputClass} />
                </FormField>
                <FormField label="Stacja klimatyczna" tooltip="Predefiniowany zbiór danych TMY (Typical Meteorological Year) używany do symulacji godzinowej. Wybierz najbliższą lokalizację.">
                  <Controller
                    name="climate_station_id"
                    control={form.control}
                    render={({ field }) => (
                      <Select
                        value={field.value}
                        onValueChange={field.onChange}
                        disabled={stationLoading}
                      >
                        <SelectTrigger className={inputClass}>
                          <SelectValue placeholder="Wybierz stację" />
                        </SelectTrigger>
                        <SelectContent>
                          {stations.map((s) => (
                            <SelectItem key={s.id} value={s.id}>
                              {s.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </FormField>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="zones">
            <AccordionTrigger>Strefy termiczne</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Strefa termiczna = obszar budynku o jednolitych warunkach
                wewnętrznych (np. piętro, mieszkanie, ogrzewana część). Każda
                strefa musi mieć przypisane przegrody i/lub okna.
              </p>
              <div className="space-y-4">
                {zonesFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
                      <FormField label="ID" tooltip="Krótki identyfikator, np. z1, z2. Używany do łączenia stref z przegrodami.">
                        <Input placeholder="np. z1" {...form.register(`thermal_zones.${index}.id`)} />
                      </FormField>
                      <FormField label="Nazwa" tooltip="Czytelna nazwa strefy, np. „Parter” lub „Mieszkanie 1”.">
                        <Input placeholder="np. Parter" {...form.register(`thermal_zones.${index}.name`)} />
                      </FormField>
                      <FormField label="Typ" tooltip="Typ strefy: heated (ogrzewana), cooled (chłodzona), unconditioned (nieogrzewana).">
                        <Input placeholder="heated" {...form.register(`thermal_zones.${index}.zone_type`)} />
                      </FormField>
                      <FormField label="Powierzchnia (m²)" tooltip="Powierzchnia podłogi strefy, używana do podziału strat ciepła i obciążeń.">
                        <Input type="number" step="0.1" placeholder="np. 150" {...form.register(`thermal_zones.${index}.floor_area`)} />
                      </FormField>
                      <FormField label="Kubatura (m³)" tooltip="Objętość powietrza w strefie – podstawa do obliczeń wentylacji i strat.">
                        <Input type="number" step="0.1" placeholder="np. 375" {...form.register(`thermal_zones.${index}.volume`)} />
                      </FormField>
                      <FormField label="Temp. ogrzewania (°C)" tooltip="Zadana temperatura wewnętrzna w sezonie grzewczym.">
                        <Input type="number" step="0.1" placeholder="np. 20" {...form.register(`thermal_zones.${index}.setpoint_heating`)} />
                      </FormField>
                      <FormField label="Temp. chłodzenia (°C)" tooltip="Górna temperatura akceptowalna w sezonie chłodniczym. Jeśli brak chłodzenia, zostaw puste.">
                        <Input type="number" step="0.1" placeholder="np. 26" {...form.register(`thermal_zones.${index}.setpoint_cooling`)} />
                      </FormField>
                      <FormField label="Gęstość zaludnienia (os./m²)" tooltip="Liczba osób na m² powierzchni użytkowej. Np. 0.03 to 1 osoba na 33 m².">
                        <Input type="number" step="0.001" placeholder="np. 0.03" {...form.register(`thermal_zones.${index}.occupancy_density`)} />
                      </FormField>
                    </CardContent>
                  </Card>
                ))}
                <Button type="button" variant="outline" onClick={() => zonesFieldArray.append(defaultValues.thermal_zones[0])}>
                  Dodaj strefę
                </Button>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="opaque">
            <AccordionTrigger>Przegrody nieprzezroczyste</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Ściany zewnętrzne, dachy, stropy, podłogi na gruncie itp. Dla
                każdej przegrody podaj powierzchnię i współczynnik przenikania
                ciepła U. Nazwy typów: external_wall, roof, ground_floor,
                floor_ceiling, party_wall.
              </p>
              <div className="space-y-4">
                {opaqueFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <FormField label="ID" tooltip="Unikalny skrót, np. wall_n, roof. Używany w raportach.">
                        <Input placeholder="np. wall_n" {...form.register(`opaque_building_elements.${index}.id`)} />
                      </FormField>
                      <FormField label="Nazwa" tooltip="Czytelna nazwa, np. „Ściana północna”.">
                        <Input placeholder="np. Ściana północna" {...form.register(`opaque_building_elements.${index}.name`)} />
                      </FormField>
                      <FormField label="ID strefy" tooltip="Strefa, do której ta przegroda należy (musi pasować do ID w sekcji stref).">
                        <Input placeholder="np. z1" {...form.register(`opaque_building_elements.${index}.zone_id`)} />
                      </FormField>
                      <FormField label="Typ" tooltip="Rodzaj przegrody: external_wall, roof, ground_floor, floor_ceiling, party_wall.">
                        <Input placeholder="np. external_wall" {...form.register(`opaque_building_elements.${index}.element_type`)} />
                      </FormField>
                      <FormField label="Azymut (°)" tooltip="Kierunek ściany: 0 = północ, 90 = wschód, 180 = południe, 270 = zachód. Dla poziomych (dach, podłoga) wpisz 0.">
                        <Input type="number" step="0.1" placeholder="0-360" {...form.register(`opaque_building_elements.${index}.orientation_azimuth`)} />
                      </FormField>
                      <FormField label="Nachylenie (°)" tooltip="Kąt do płaszczyzny poziomej. Ściana = 90°, dach płaski = 0°, podłoga na gruncie = 180°.">
                        <Input type="number" step="0.1" placeholder="0-180" {...form.register(`opaque_building_elements.${index}.inclination`)} />
                      </FormField>
                      <FormField label="Powierzchnia (m²)" tooltip="Powierzchnia brutto przegrody (bez pomniejszania o okna – okna dodawane są osobno).">
                        <Input type="number" step="0.1" placeholder="np. 40" {...form.register(`opaque_building_elements.${index}.area`)} />
                      </FormField>
                      <FormField label="U (W/m²K)" tooltip="Współczynnik przenikania ciepła. Niższa wartość = mniejsze straty ciepła.">
                        <Input type="number" step="0.01" placeholder="np. 0.25" {...form.register(`opaque_building_elements.${index}.u_value`)} />
                      </FormField>
                      <FormField label="Absorpcja słońca (α)" tooltip="Współczynnik absorpcji promieniowania słonecznego powierzchni (0 = odbija wszystko, 1 = pochłania wszystko). Dla farb jasnych ~0.4, ciemnych ~0.8.">
                        <Input type="number" step="0.01" placeholder="0-1" {...form.register(`opaque_building_elements.${index}.solar_absorptance`)} />
                      </FormField>
                      <FormField label="Redukcja zysków (F_ol)" tooltip="Udział promieniowania słonecznego pochłanianego przez płaszcz zewnętrzny. Standardowo ok. 0.08.">
                        <Input type="number" step="0.01" placeholder="np. 0.08" {...form.register(`opaque_building_elements.${index}.solar_reduction_factor`)} />
                      </FormField>
                      <FormField label="Przestrzeń sąsiednia" tooltip="Co jest po drugiej stronie: outdoor (zewnętrze), ground (grunt), unheated (nieogrzewane pomieszczenie), adjacent (inna ogrzewana strefa).">
                        <Input placeholder="outdoor" {...form.register(`opaque_building_elements.${index}.adjacent_space_type`)} />
                      </FormField>
                    </CardContent>
                  </Card>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => opaqueFieldArray.append(defaultValues.opaque_building_elements[0])}
                >
                  Dodaj przegrodę
                </Button>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="transparent">
            <AccordionTrigger>Przegrody transparentne</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Okna, drzwi przeszklone, świetliki. Powierzchnia okna to
                ościeżnica, a współczynnik g i udział ramy redukują zyski
                solarne.
              </p>
              <div className="space-y-4">
                {transparentFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <FormField label="ID" tooltip="Unikalny skrót, np. win_s, drzwi_e.">
                        <Input placeholder="np. win_s" {...form.register(`transparent_building_elements.${index}.id`)} />
                      </FormField>
                      <FormField label="Nazwa" tooltip="Czytelna nazwa, np. „Okno południowe”.">
                        <Input placeholder="np. Okno południowe" {...form.register(`transparent_building_elements.${index}.name`)} />
                      </FormField>
                      <FormField label="ID strefy" tooltip="Strefa, do której należy okno (musi pasować do ID strefy).">
                        <Input placeholder="np. z1" {...form.register(`transparent_building_elements.${index}.zone_id`)} />
                      </FormField>
                      <FormField label="Typ" tooltip="Rodzaj elementu: window, door, skylight.">
                        <Input placeholder="np. window" {...form.register(`transparent_building_elements.${index}.element_type`)} />
                      </FormField>
                      <FormField label="Azymut (°)" tooltip="Kierunek okna: 0 = północ, 90 = wschód, 180 = południe, 270 = zachód.">
                        <Input type="number" step="0.1" placeholder="0-360" {...form.register(`transparent_building_elements.${index}.orientation_azimuth`)} />
                      </FormField>
                      <FormField label="Nachylenie (°)" tooltip="Kąt do poziomu. Standardowe okno = 90°, świetlik = 0°.">
                        <Input type="number" step="0.1" placeholder="0-180" {...form.register(`transparent_building_elements.${index}.inclination`)} />
                      </FormField>
                      <FormField label="Powierzchnia (m²)" tooltip="Powierzchnia całkowita okna wraz z ramą.">
                        <Input type="number" step="0.1" placeholder="np. 10" {...form.register(`transparent_building_elements.${index}.area`)} />
                      </FormField>
                      <FormField label="U (W/m²K)" tooltip="Współczynnik przenikania ciepła okna (U_w).">
                        <Input type="number" step="0.01" placeholder="np. 1.0" {...form.register(`transparent_building_elements.${index}.u_value`)} />
                      </FormField>
                      <FormField label="g" tooltip="Współczynnik przenikania energii słonecznej szyby (g_lw). Np. dla szyby zwykłej ~0.75, dla przeciwsłonecznej ~0.4.">
                        <Input type="number" step="0.01" placeholder="0-1" {...form.register(`transparent_building_elements.${index}.g_value`)} />
                      </FormField>
                      <FormField label="Udział ramy" tooltip="Udział powierzchni ramy w całkowitej powierzchni okna (0-1). Typowo 0.15-0.30.">
                        <Input type="number" step="0.01" placeholder="0-1" {...form.register(`transparent_building_elements.${index}.frame_factor`)} />
                      </FormField>
                      <FormField label="Współczynnik ekranowania" tooltip="Udział promieniowania słonecznego docierającego do wnętrza po uwzględnieniu zacienień zewnętrznych (0 = całkowicie zacienione, 1 = brak zacienienia).">
                        <Input type="number" step="0.01" placeholder="0-1" {...form.register(`transparent_building_elements.${index}.shading_factor`)} />
                      </FormField>
                    </CardContent>
                  </Card>
                ))}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => transparentFieldArray.append(defaultValues.transparent_building_elements[0])}
                >
                  Dodaj okno
                </Button>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="ventilation">
            <AccordionTrigger>Wentylacja</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Parametry wentylacji i infiltracji. Strumień powietrza może być
                podany jako przepływ objętościowy (m³/h) lub obliczony z liczby
                zmian powietrza.
              </p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField label="Typ wentylacji" tooltip="Typ instalacji: natural (gravitacyjna), mechanical (mechaniczna z wentylatorami), mechanical_with_recovery (z rekuperacją).">
                  <Input placeholder="np. natural" {...form.register("ventilation.ventilation_type")} className={inputClass} />
                </FormField>
                <FormField label="Strumień powietrza (m³/h)" tooltip="Roczny lub zimowy strumień powietrza wentylacyjnego. Np. 120 m³/h dla niedużego mieszkania.">
                  <Input type="number" step="0.1" placeholder="np. 120" {...form.register("ventilation.airflow_rate")} className={inputClass} />
                </FormField>
                <FormField label="Sprawność odzysku" tooltip="Sprawność rekuperatora (0 = brak, 0.8 = wysoka). Dla wentylacji grawitacyjnej zostaw 0.">
                  <Input type="number" step="0.01" placeholder="0-1" {...form.register("ventilation.heat_recovery_efficiency")} className={inputClass} />
                </FormField>
                <FormField label="Współczynnik infiltracji (1/h)" tooltip="Liczba wymian powietrza na godzinę w wyniku nieszczelności. Dla budynków szczelnych 0.1-0.3, dla starszych 0.5-1.0.">
                  <Input type="number" step="0.01" placeholder="np. 0.5" {...form.register("ventilation.infiltration_rate")} className={inputClass} />
                </FormField>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        {error && (
          <Alert variant="destructive" className="mt-6">
            <AlertTitle>Błąd</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="mt-8 flex gap-4">
          <Button type="submit" size="lg" disabled={loading}>
            {loading ? "Obliczanie..." : "Oblicz charakterystykę"}
          </Button>
        </div>
      </form>
    </main>
  )
}

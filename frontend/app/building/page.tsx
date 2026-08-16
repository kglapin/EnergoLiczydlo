"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useForm, useFieldArray } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { calculate } from "@/lib/api"
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
      <h1 className="text-3xl font-bold mb-6">Nowa analiza energetyczna</h1>
      <form onSubmit={form.handleSubmit(onSubmit)}>
        <Accordion type="multiple" defaultValue={["general"]} className="space-y-4">
          <AccordionItem value="general">
            <AccordionTrigger>Informacje ogólne</AccordionTrigger>
            <AccordionContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="project_name">Nazwa projektu</Label>
                  <Input id="project_name" {...form.register("project_name")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="building_name">Nazwa budynku</Label>
                  <Input id="building_name" {...form.register("general.building_name")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="building_type">Typ budynku</Label>
                  <Input id="building_type" {...form.register("general.building_type")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="construction_year">Rok budowy</Label>
                  <Input id="construction_year" type="number" {...form.register("general.construction_year")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="conditioned_floor_area">Powierzchnia ogrzewana (m²)</Label>
                  <Input id="conditioned_floor_area" type="number" step="0.1" {...form.register("general.conditioned_floor_area")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="usable_floor_area">Powierzchnia użytkowa (m²)</Label>
                  <Input id="usable_floor_area" type="number" step="0.1" {...form.register("general.usable_floor_area")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="heated_volume">Kubatura ogrzewana (m³)</Label>
                  <Input id="heated_volume" type="number" step="0.1" {...form.register("general.heated_volume")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="number_of_storeys">Liczba kondygnacji</Label>
                  <Input id="number_of_storeys" type="number" {...form.register("general.number_of_storeys")} className={inputClass} />
                </div>
                <div>
                  <Label htmlFor="climate_station_id">Stacja klimatyczna</Label>
                  <Input id="climate_station_id" {...form.register("climate_station_id")} className={inputClass} />
                </div>
              </div>
            </AccordionContent>
          </AccordionItem>

          <AccordionItem value="zones">
            <AccordionTrigger>Strefy termiczne</AccordionTrigger>
            <AccordionContent>
              <div className="space-y-4">
                {zonesFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-4">
                      <Input placeholder="ID" {...form.register(`thermal_zones.${index}.id`)} />
                      <Input placeholder="Nazwa" {...form.register(`thermal_zones.${index}.name`)} />
                      <Input placeholder="Typ" {...form.register(`thermal_zones.${index}.zone_type`)} />
                      <Input type="number" step="0.1" placeholder="Powierzchnia (m²)" {...form.register(`thermal_zones.${index}.floor_area`)} />
                      <Input type="number" step="0.1" placeholder="Kubatura (m³)" {...form.register(`thermal_zones.${index}.volume`)} />
                      <Input type="number" step="0.1" placeholder="Temp. ogrzewania" {...form.register(`thermal_zones.${index}.setpoint_heating`)} />
                      <Input type="number" step="0.1" placeholder="Temp. chłodzenia" {...form.register(`thermal_zones.${index}.setpoint_cooling`)} />
                      <Input type="number" step="0.001" placeholder="Os./m²" {...form.register(`thermal_zones.${index}.occupancy_density`)} />
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
              <div className="space-y-4">
                {opaqueFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <Input placeholder="ID" {...form.register(`opaque_building_elements.${index}.id`)} />
                      <Input placeholder="Nazwa" {...form.register(`opaque_building_elements.${index}.name`)} />
                      <Input placeholder="ID strefy" {...form.register(`opaque_building_elements.${index}.zone_id`)} />
                      <Input placeholder="Typ" {...form.register(`opaque_building_elements.${index}.element_type`)} />
                      <Input type="number" step="0.1" placeholder="Azymut" {...form.register(`opaque_building_elements.${index}.orientation_azimuth`)} />
                      <Input type="number" step="0.1" placeholder="Nachylenie" {...form.register(`opaque_building_elements.${index}.inclination`)} />
                      <Input type="number" step="0.1" placeholder="Powierzchnia (m²)" {...form.register(`opaque_building_elements.${index}.area`)} />
                      <Input type="number" step="0.01" placeholder="U (W/m²K)" {...form.register(`opaque_building_elements.${index}.u_value`)} />
                      <Input placeholder="Przestrzeń sąsiednia" {...form.register(`opaque_building_elements.${index}.adjacent_space_type`)} />
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
              <div className="space-y-4">
                {transparentFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <Input placeholder="ID" {...form.register(`transparent_building_elements.${index}.id`)} />
                      <Input placeholder="Nazwa" {...form.register(`transparent_building_elements.${index}.name`)} />
                      <Input placeholder="ID strefy" {...form.register(`transparent_building_elements.${index}.zone_id`)} />
                      <Input placeholder="Typ" {...form.register(`transparent_building_elements.${index}.element_type`)} />
                      <Input type="number" step="0.1" placeholder="Azymut" {...form.register(`transparent_building_elements.${index}.orientation_azimuth`)} />
                      <Input type="number" step="0.1" placeholder="Nachylenie" {...form.register(`transparent_building_elements.${index}.inclination`)} />
                      <Input type="number" step="0.1" placeholder="Powierzchnia (m²)" {...form.register(`transparent_building_elements.${index}.area`)} />
                      <Input type="number" step="0.01" placeholder="U (W/m²K)" {...form.register(`transparent_building_elements.${index}.u_value`)} />
                      <Input type="number" step="0.01" placeholder="g" {...form.register(`transparent_building_elements.${index}.g_value`)} />
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
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <Label>Typ wentylacji</Label>
                  <Input {...form.register("ventilation.ventilation_type")} className={inputClass} />
                </div>
                <div>
                  <Label>Strumień powietrza (m³/h)</Label>
                  <Input type="number" step="0.1" {...form.register("ventilation.airflow_rate")} className={inputClass} />
                </div>
                <div>
                  <Label>Sprawność odzysku</Label>
                  <Input type="number" step="0.01" {...form.register("ventilation.heat_recovery_efficiency")} className={inputClass} />
                </div>
                <div>
                  <Label>Współczynnik infiltracji (1/h)</Label>
                  <Input type="number" step="0.01" {...form.register("ventilation.infiltration_rate")} className={inputClass} />
                </div>
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

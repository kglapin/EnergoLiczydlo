"use client"

import { Suspense, useCallback, useEffect, useRef, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2, MapPin, Trash2 } from "lucide-react"
import {
  useForm,
  useFieldArray,
  Controller,
  useWatch,
  type FieldErrors,
  type FieldPath,
} from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { FormField } from "@/components/form-field"
import { FormSelect } from "@/components/form-select"
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
import {
  calculate,
  CalculationRequestError,
  type ApiValidationIssue,
  fetchStations,
  resolveClimateStation,
} from "@/lib/api"
import { useAppStore, type BuildingProject } from "@/lib/store"
import { CalculationResults } from "@/components/calculation-results"
import {
  coolingSourceOptions,
  dhwDistributionOptions,
  dhwSourceOptions,
  energyCarrierOptions,
  heatingSourceOptions,
  normativeInternalGains,
} from "@/lib/system-options"

const buildingTypeValues = ["residential", "office", "school", "retail", "healthcare", "other"] as const
const dhwUsageProfileValues = [
  "residential_single_family",
  "residential_multi_family_lump_sum",
  "residential_multi_family_individual_metering",
  "office",
  "education",
  "healthcare",
  "retail_services",
  "collective_residential",
  "warehouse",
] as const
const dhwUsageProfileByBuildingType: Partial<
  Record<(typeof buildingTypeValues)[number], (typeof dhwUsageProfileValues)[number]>
> = {
  residential: "residential_single_family",
  office: "office",
  school: "education",
  retail: "retail_services",
  healthcare: "healthcare",
}
const zoneTypeValues = ["heated", "cooled", "heated_and_cooled", "unheated", "semi_heated"] as const
const opaqueElementTypeValues = [
  "external_wall",
  "roof",
  "ground_floor",
  "floor_over_unheated",
  "internal_wall",
  "basement_wall",
  "party_wall",
] as const
const transparentElementTypeValues = ["window", "glass_door", "skylight"] as const
const adjacentSpaceTypeValues = [
  "outdoor",
  "ground",
  "unheated_zone",
  "heated_zone",
  "constant_temperature",
] as const
const ventilationTypeValues = [
  "natural",
  "mechanical",
  "mechanical_with_recovery",
  "exhaust",
  "hybrid",
  "none",
] as const

const zoneSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  zone_type: z.enum(zoneTypeValues),
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
  element_type: z.enum(opaqueElementTypeValues),
  orientation_azimuth: z.coerce.number(),
  inclination: z.coerce.number(),
  height: z.coerce.number().positive(),
  width: z.coerce.number().positive(),
  area: z.coerce.number().positive(),
  u_value: z.coerce.number().positive(),
  solar_absorptance: z.coerce.number().min(0).max(1).optional(),
  solar_reduction_factor: z.coerce.number().min(0).max(1).optional(),
  adjacent_space_type: z.enum(adjacentSpaceTypeValues).optional(),
})

const transparentSchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  zone_id: z.string().min(1),
  element_type: z.enum(transparentElementTypeValues),
  orientation_azimuth: z.coerce.number(),
  inclination: z.coerce.number(),
  height: z.coerce.number().positive(),
  width: z.coerce.number().positive(),
  area: z.coerce.number().positive(),
  u_value: z.coerce.number().positive(),
  g_value: z.coerce.number().min(0).max(1),
  frame_factor: z.coerce.number().min(0).max(1).optional(),
  shading_factor: z.coerce.number().min(0).max(1).optional(),
})

const heatingSystemSchema = z.object({
  system_type: z.string().min(1),
  fuel_or_carrier: z.string().min(1),
  generation_efficiency: z.coerce.number().positive(),
  distribution_efficiency: z.coerce.number().positive().max(1),
  storage_efficiency: z.coerce.number().positive().max(1),
  control_efficiency: z.coerce.number().positive().max(1),
  sink_temperature: z.coerce.number().positive().optional(),
})

const coolingSystemSchema = heatingSystemSchema

const dhwSchema = z.object({
  system_type: z.string().min(1),
  fuel_or_carrier: z.string().min(1),
  generation_efficiency: z.coerce.number().positive(),
  storage_efficiency: z.coerce.number().positive().max(1),
  distribution_efficiency: z.coerce.number().positive().max(1),
  utilization_efficiency: z.coerce.number().positive().max(1),
  distribution_type: z.string().min(1),
  storage_volume_dm3: z.coerce.number().positive().optional(),
  storage_location: z.enum(["heated", "unheated"]).optional(),
  storage_insulation_mm: z.coerce.number().positive().optional(),
})

const formSchema = z.object({
  project_name: z.string().min(1),
  general: z.object({
    building_name: z.string().min(1),
    building_type: z.enum(buildingTypeValues),
    dhw_usage_profile: z.enum(dhwUsageProfileValues),
    construction_year: z.coerce.number(),
    conditioned_floor_area: z.coerce.number().positive(),
    usable_floor_area: z.coerce.number().positive(),
    heated_volume: z.coerce.number().positive(),
    number_of_storeys: z.coerce.number().int().positive(),
    location_address: z.string().optional(),
    lighting_indicator_leni: z.coerce.number().min(0).optional(),
    lighting_area_m2: z.coerce.number().positive().optional(),
  }),
  climate_station_id: z.string().min(1),
  thermal_zones: z.array(zoneSchema).min(1),
  opaque_building_elements: z.array(opaqueSchema),
  transparent_building_elements: z.array(transparentSchema),
  ventilation: z.object({
    ventilation_type: z.enum(ventilationTypeValues),
    airflow_rate: z.coerce.number().min(0),
    heat_recovery_efficiency: z.coerce.number().min(0).max(1),
    infiltration_rate: z.coerce.number().min(0),
    usage_share_beta: z.coerce.number().min(0).max(1).optional(),
  }),
  systems: z.object({
    heating: heatingSystemSchema,
    cooling: coolingSystemSchema,
    dhw: dhwSchema,
  }),
})

type FormValues = z.infer<typeof formSchema>

type ValidationErrorEntry = {
  path: string
  message: string
}

const validationFieldLabels: Record<string, string> = {
  project_name: "Nazwa projektu",
  "general.building_name": "Nazwa budynku",
  "general.building_type": "Typ budynku",
  "general.dhw_usage_profile": "Profil standardowego użytkowania CWU",
  "general.construction_year": "Rok budowy",
  "general.conditioned_floor_area": "Powierzchnia ogrzewana",
  "general.usable_floor_area": "Powierzchnia użytkowa",
  "general.heated_volume": "Kubatura ogrzewana",
  "general.number_of_storeys": "Liczba kondygnacji",
  climate_station_id: "Stacja klimatyczna",
  "ventilation.ventilation_type": "Typ wentylacji",
  "ventilation.airflow_rate": "Strumień powietrza",
  "ventilation.heat_recovery_efficiency": "Sprawność odzysku ciepła",
  "ventilation.infiltration_rate": "Współczynnik infiltracji",
  "systems.heating.system_type": "Źródło ciepła",
  "systems.heating.fuel_or_carrier": "Nośnik energii ogrzewania",
  "systems.cooling.system_type": "Źródło chłodu",
  "systems.cooling.fuel_or_carrier": "Nośnik energii chłodzenia",
  "systems.dhw.system_type": "Źródło CWU",
  "systems.dhw.fuel_or_carrier": "Nośnik energii CWU",
  "systems.dhw.distribution_type": "Typ przesyłu CWU",
  __root__: "Zależność między danymi",
  id: "ID",
  name: "Nazwa",
  zone_id: "ID strefy",
  floor_area: "Powierzchnia strefy",
  volume: "Kubatura strefy",
  height: "Wysokość",
  width: "Szerokość",
  area: "Powierzchnia",
  u_value: "Współczynnik U",
  g_value: "Współczynnik g",
  generation_efficiency: "Sprawność wytwarzania",
  distribution_efficiency: "Sprawność przesyłu",
  storage_efficiency: "Sprawność akumulacji",
  control_efficiency: "Sprawność regulacji",
  utilization_efficiency: "Sprawność wykorzystania",
}

function collectValidationErrors(
  errors: unknown,
  path: string[] = [],
): ValidationErrorEntry[] {
  if (!errors || typeof errors !== "object") return []
  const record = errors as Record<string, unknown>
  if (typeof record.message === "string") {
    return [{ path: path.join("."), message: record.message }]
  }
  return Object.entries(record).flatMap(([key, value]) =>
    collectValidationErrors(value, [...path, key]),
  )
}

function formatValidationPath(path: string): string {
  const parts = path.split(".")
  const collectionLabels: Record<string, string> = {
    thermal_zones: "Strefa termiczna",
    opaque_building_elements: "Przegroda nieprzezroczysta",
    transparent_building_elements: "Przegroda transparentna",
  }
  if (parts.length >= 3 && collectionLabels[parts[0]] && /^\d+$/.test(parts[1])) {
    const field = parts.slice(2).join(".")
    return `${collectionLabels[parts[0]]} ${Number(parts[1]) + 1} — ${validationFieldLabels[field] ?? field}`
  }
  return validationFieldLabels[path] ?? path
}

function formatValidationMessage(message: string): string {
  if (message.includes("at least 1 character")) return "Pole jest wymagane."
  if (message.includes("received nan") || message.includes("received undefined")) {
    return "Podaj poprawną liczbę."
  }
  if (message.includes("greater than 0")) return "Wartość musi być większa od 0."
  if (message.includes("greater than or equal to 0")) {
    return "Wartość nie może być ujemna."
  }
  if (message.includes("less than or equal to 1")) {
    return "Wartość nie może być większa niż 1."
  }
  return message
}

function formatBackendValidationMessage(issue: ApiValidationIssue): string {
  const message = issue.msg.replace(/^Value error,\s*/i, "")
  if (issue.type === "missing" || message === "Field required") {
    return "Pole jest wymagane."
  }
  if (issue.type === "enum") {
    return "Wybrana wartość nie jest obsługiwana. Wybierz jedną z opcji z listy."
  }
  if (issue.type === "greater_than") {
    return `Wartość musi być większa niż ${String(issue.ctx?.gt ?? 0)}.`
  }
  if (issue.type === "greater_than_equal") {
    return `Wartość nie może być mniejsza niż ${String(issue.ctx?.ge ?? 0)}.`
  }
  if (issue.type === "less_than_equal") {
    return `Wartość nie może być większa niż ${String(issue.ctx?.le ?? 1)}.`
  }
  if (message.startsWith("Invalid heating system source:")) {
    return "Wybrane źródło ciepła nie jest obsługiwane przez metodę obliczeń. Wybierz pozycję z listy."
  }
  if (message.startsWith("Invalid cooling system source:")) {
    return "Wybrane źródło chłodu nie jest obsługiwane przez metodę obliczeń. Wybierz pozycję z listy."
  }
  if (message.startsWith("Unknown thermal zone ID referenced by an element:")) {
    return "Przegroda wskazuje strefę, która nie istnieje. Wybierz ID z listy zdefiniowanych stref termicznych."
  }
  if (message === "Thermal zone IDs must be unique") {
    return "Każda strefa termiczna musi mieć unikalne ID."
  }
  return message
}

function serverErrorPath(issue: ApiValidationIssue, values: FormValues): string {
  const rawPath = issue.loc
    .filter((part) => part !== "body")
    .map(String)
    .join(".")

  if (rawPath === "systems") {
    if (issue.msg.includes("heating system source")) return "systems.heating.system_type"
    if (issue.msg.includes("cooling system source")) return "systems.cooling.system_type"
  }

  const unknownZone = issue.msg.match(/Unknown thermal zone ID referenced by an element:\s*(.+)$/)
  if (unknownZone) {
    const zoneId = unknownZone[1].trim()
    const opaqueIndex = values.opaque_building_elements.findIndex(
      (element) => element.zone_id === zoneId,
    )
    if (opaqueIndex >= 0) return `opaque_building_elements.${opaqueIndex}.zone_id`
    const transparentIndex = values.transparent_building_elements.findIndex(
      (element) => element.zone_id === zoneId,
    )
    if (transparentIndex >= 0) return `transparent_building_elements.${transparentIndex}.zone_id`
  }

  if (issue.msg.includes("Thermal zone IDs must be unique")) {
    const duplicateIndex = values.thermal_zones.findIndex(
      (zone, index, zones) => zones.findIndex((candidate) => candidate.id === zone.id) !== index,
    )
    if (duplicateIndex >= 0) return `thermal_zones.${duplicateIndex}.id`
  }

  return rawPath || "__root__"
}

function normalizeServerValidationErrors(
  issues: ApiValidationIssue[],
  values: FormValues,
): ValidationErrorEntry[] {
  const entries = issues.map((issue) => ({
    path: serverErrorPath(issue, values),
    message: formatBackendValidationMessage(issue),
  }))
  return Array.from(
    new Map(entries.map((entry) => [`${entry.path}\u0000${entry.message}`, entry])).values(),
  )
}

function sectionForValidationPath(path: string): string | null {
  if (path === "project_name" || path.startsWith("general.") || path === "climate_station_id") {
    return "general"
  }
  if (path.startsWith("thermal_zones.")) return "zones"
  if (path.startsWith("opaque_building_elements.")) return "opaque"
  if (path.startsWith("transparent_building_elements.")) return "transparent"
  if (path.startsWith("systems.")) return "systems"
  if (path.startsWith("ventilation.")) return "ventilation"
  return null
}

function controlForValidationPath(path: string): HTMLElement | null {
  if (typeof document === "undefined" || path === "__root__") return null

  const escapedPath = path.replaceAll("\\", "\\\\").replaceAll('"', '\\"')
  const selectTrigger = document.querySelector<HTMLElement>(
    `[data-field-path="${escapedPath}"]`,
  )
  if (selectTrigger) return selectTrigger

  return Array.from(document.getElementsByName(path)).find(
    (element): element is HTMLElement =>
      element instanceof HTMLElement &&
      !(element instanceof HTMLInputElement && element.type === "hidden"),
  ) ?? null
}

function calculateElementArea(height: unknown, width: unknown): number | null {
  const heightValue = Number(height)
  const widthValue = Number(width)
  if (!Number.isFinite(heightValue) || !Number.isFinite(widthValue)) return null
  if (heightValue <= 0 || widthValue <= 0) return null
  return heightValue * widthValue
}

const defaultValues: FormValues = {
  project_name: "Mój budynek",
  general: {
    building_name: "Dom jednorodzinny",
    building_type: "residential",
    dhw_usage_profile: "residential_single_family",
    construction_year: 2020,
    conditioned_floor_area: 150,
    usable_floor_area: 150,
    heated_volume: 375,
    number_of_storeys: 1,
    location_address: "",
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
      height: 4,
      width: 10,
      area: 40,
      u_value: 0.25,
      solar_absorptance: 0.6,
      adjacent_space_type: "outdoor",
    },
    {
      id: "wall_s",
      name: "Ściana południowa",
      zone_id: "z1",
      element_type: "external_wall",
      orientation_azimuth: 180,
      inclination: 90,
      height: 4,
      width: 10,
      area: 40,
      u_value: 0.25,
      solar_absorptance: 0.6,
      adjacent_space_type: "outdoor",
    },
    {
      id: "roof",
      name: "Dach",
      zone_id: "z1",
      element_type: "roof",
      orientation_azimuth: 0,
      inclination: 0,
      height: 9,
      width: 10,
      area: 90,
      u_value: 0.18,
      solar_absorptance: 0.6,
      adjacent_space_type: "outdoor",
    },
    {
      id: "floor",
      name: "Podłoga na gruncie",
      zone_id: "z1",
      element_type: "ground_floor",
      orientation_azimuth: 0,
      inclination: 180,
      height: 9,
      width: 10,
      area: 90,
      u_value: 0.25,
      solar_absorptance: 0.6,
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
      height: 2,
      width: 5,
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
    usage_share_beta: undefined,
  },
  systems: {
    heating: {
      system_type: "heat_pump_air",
      fuel_or_carrier: "electricity",
      generation_efficiency: 3.0,
      distribution_efficiency: 0.95,
      storage_efficiency: 1.0,
      control_efficiency: 1.0,
      sink_temperature: 35,
    },
    cooling: {
      system_type: "none",
      fuel_or_carrier: "electricity",
      generation_efficiency: 3.9,
      distribution_efficiency: 1.0,
      storage_efficiency: 1.0,
      control_efficiency: 0.94,
    },
    dhw: {
      system_type: "electric_storage",
      fuel_or_carrier: "electricity",
      generation_efficiency: 0.96,
      storage_efficiency: 1.0,
      distribution_efficiency: 0.8,
      utilization_efficiency: 1.0,
      distribution_type: "single_dwelling",
      storage_volume_dm3: undefined,
      storage_location: undefined,
      storage_insulation_mm: undefined,
    },
  },
}

type DimensionedElement = {
  area?: number
  height?: number
  width?: number
}

function withElementDimensions<T extends DimensionedElement>(
  elements: T[] | undefined,
  fallback: T[],
): Array<T & { height: number; width: number }> {
  const source = elements ?? fallback
  return source.map((element, index) => {
    const fallbackElement = fallback[index] ?? fallback[0]
    const elementArea = Number(element.area)
    const fallbackArea = Number(fallbackElement.area)
    const area = Number.isFinite(elementArea) && elementArea > 0
      ? elementArea
      : fallbackArea
    const defaultDimension = Math.sqrt(area)
    const height = Number(element.height) > 0 ? Number(element.height) : defaultDimension
    const width = Number(element.width) > 0 ? Number(element.width) : defaultDimension

    return {
      ...fallbackElement,
      ...element,
      height,
      width,
      area: height * width,
    }
  })
}

const legacyBuildingTypeValues: Record<string, (typeof buildingTypeValues)[number]> = {
  commercial: "retail",
  public: "other",
}

const legacyZoneTypeValues: Record<string, (typeof zoneTypeValues)[number]> = {
  unconditioned: "unheated",
}

const legacyOpaqueElementTypeValues: Record<string, (typeof opaqueElementTypeValues)[number]> = {
  floor_ceiling: "floor_over_unheated",
}

const legacyTransparentElementTypeValues: Record<
  string,
  (typeof transparentElementTypeValues)[number]
> = {
  door: "glass_door",
}

const legacyAdjacentSpaceTypeValues: Record<
  string,
  (typeof adjacentSpaceTypeValues)[number]
> = {
  unheated: "unheated_zone",
  adjacent: "heated_zone",
}

function migrateLegacyValue<T extends string>(value: T, replacements: Record<string, T>): T {
  return replacements[value] ?? value
}

function withoutLegacyInputs<T extends object>(
  value: T | undefined,
  legacyFields: readonly string[],
): T | undefined {
  if (!value) return value
  const sanitized = { ...value } as Record<string, unknown>
  for (const field of legacyFields) delete sanitized[field]
  return sanitized as T
}

function mergeFormValues(project: unknown): FormValues {
  const incoming = (project ?? {}) as Partial<FormValues>
  const incomingSystems = (incoming.systems ?? {}) as Partial<FormValues["systems"]>
  const buildingType = migrateLegacyValue(
    (incoming.general?.building_type ?? defaultValues.general.building_type) as FormValues["general"]["building_type"],
    legacyBuildingTypeValues,
  )
  const incomingHeating = withoutLegacyInputs(incomingSystems.heating, ["nominal_power"])
  const incomingCooling = withoutLegacyInputs(incomingSystems.cooling, ["nominal_power"])
  const incomingDhw = withoutLegacyInputs(incomingSystems.dhw, [
    "daily_demand_per_person",
    "number_of_users",
    "target_temperature",
    "cold_water_temperature",
  ])
  return {
    ...defaultValues,
    ...incoming,
    general: {
      ...defaultValues.general,
      ...(incoming.general ?? {}),
      building_type: buildingType,
      dhw_usage_profile: incoming.general?.dhw_usage_profile
        ?? dhwUsageProfileByBuildingType[buildingType]
        ?? defaultValues.general.dhw_usage_profile,
    },
    thermal_zones: (incoming.thermal_zones ?? defaultValues.thermal_zones).map((zone) => ({
      ...zone,
      zone_type: migrateLegacyValue(zone.zone_type, legacyZoneTypeValues),
    })),
    opaque_building_elements: withElementDimensions(
      incoming.opaque_building_elements,
      defaultValues.opaque_building_elements,
    ).map((element) => ({
      ...element,
      element_type: migrateLegacyValue(element.element_type, legacyOpaqueElementTypeValues),
      adjacent_space_type: element.adjacent_space_type
        ? migrateLegacyValue(element.adjacent_space_type, legacyAdjacentSpaceTypeValues)
        : element.adjacent_space_type,
    })),
    transparent_building_elements: withElementDimensions(
      incoming.transparent_building_elements,
      defaultValues.transparent_building_elements,
    ).map((element) => ({
      ...element,
      element_type: migrateLegacyValue(element.element_type, legacyTransparentElementTypeValues),
    })),
    systems: {
      ...defaultValues.systems,
      ...incomingSystems,
      heating: { ...defaultValues.systems.heating, ...(incomingHeating ?? {}) },
      cooling: { ...defaultValues.systems.cooling, ...(incomingCooling ?? {}) },
      dhw: { ...defaultValues.systems.dhw, ...(incomingDhw ?? {}) },
    },
  }
}

function createProjectPayload(values: FormValues): BuildingProject {
  return {
    version: "0.1.0",
    metadata: {},
    thermal_bridges: { auto_calculate: false, linear_bridges: [], point_bridges: [] },
    // Normatywne zyski wewnętrzne z tabeli 26 metodologii (Dz.U. 2015 poz. 376),
    // dobrane do profilu użytkowania CWU budynku.
    internal_gains: normativeInternalGains(values.general.dhw_usage_profile),
    primary_energy: {
      // w_i wg tabeli 1 rozporządzenia (Dz.U. 2015 poz. 376); we w kg CO2/kWh.
      electricity: { fp: 3.0, we: 0.6 },
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
      renewable: { fp: 0.0, we: 0.0 },
    },
    ...values,
    // Chłodzenie liczone jest wyłącznie dla stref chłodzonych (§ 5.4
    // metodologii) - dla pozostałych typów stref setpoint jest ignorowany,
    // więc nie wysyłamy go, żeby nie sugerować, że działa.
    thermal_zones: values.thermal_zones.map((zone) => ({
      ...zone,
      setpoint_cooling:
        zone.zone_type === "cooled" || zone.zone_type === "heated_and_cooled"
          ? zone.setpoint_cooling
          : undefined,
    })),
    opaque_building_elements: values.opaque_building_elements.map((element) => ({
      ...element,
      area: Number(element.height) * Number(element.width),
    })),
    transparent_building_elements: values.transparent_building_elements.map((element) => ({
      ...element,
      area: Number(element.height) * Number(element.width),
    })),
  }
}

function BuildingFormContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const historyId = searchParams.get("history")
  const isNewProject = searchParams.get("new") === "1"
  const {
    history,
    project: currentProject,
    result: currentResult,
    setProject,
    setResult,
    autoSaveProject,
    addToHistory,
    loadHistoryItem,
    startNewProject,
  } = useAppStore()
  const [error, setError] = useState<string | null>(null)
  const [validationErrors, setValidationErrors] = useState<ValidationErrorEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [openSections, setOpenSections] = useState<string[]>(["general"])

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  })
  const { reset: resetForm } = form
  const { isDirty } = form.formState
  const watchedFormValues = useWatch({ control: form.control })
  const watchedFormSnapshot = JSON.stringify(watchedFormValues)
  const [autosaveState, setAutosaveState] = useState<"idle" | "saving" | "saved">("idle")
  const autosaveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const historyHydrationRef = useRef<string | null>(null)
  const autoCalculationAttemptedRef = useRef<string | null>(null)
  const previousFormSnapshotRef = useRef<string | undefined>(undefined)
  const historyItem = historyId
    ? history.find((item) => item.id === historyId)
    : undefined

  useEffect(() => {
    if (isNewProject) {
      historyHydrationRef.current = null
      autoCalculationAttemptedRef.current = null
      startNewProject()
      resetForm(defaultValues)
      return
    }

    if (historyId && historyItem && historyHydrationRef.current !== historyId) {
      historyHydrationRef.current = historyId
      loadHistoryItem(historyId)
      resetForm(mergeFormValues(historyItem.project))
    }
  }, [historyId, historyItem, isNewProject, loadHistoryItem, resetForm, startNewProject])

  useEffect(() => {
    const saveDraft = () => {
      if (!isDirty) return
      const draftId = autoSaveProject(createProjectPayload(form.getValues()))
      if (!historyId) {
        router.replace(`/building?history=${encodeURIComponent(draftId)}`)
      }
      setAutosaveState("saved")
    }

    if (!isDirty) {
      setAutosaveState("idle")
      return
    }

    setAutosaveState("saving")
    if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current)
    autosaveTimerRef.current = setTimeout(saveDraft, 500)
    window.addEventListener("pagehide", saveDraft)

    return () => {
      if (autosaveTimerRef.current) clearTimeout(autosaveTimerRef.current)
      window.removeEventListener("pagehide", saveDraft)
    }
  }, [autoSaveProject, form, historyId, isDirty, router, watchedFormValues])

  useEffect(() => {
    const formChanged =
      previousFormSnapshotRef.current !== undefined &&
      previousFormSnapshotRef.current !== watchedFormSnapshot

    previousFormSnapshotRef.current = watchedFormSnapshot

    if (formChanged && validationErrors.length > 0) {
      form.clearErrors()
      setValidationErrors([])
      setError(null)
    }
  }, [form, validationErrors.length, watchedFormSnapshot])

  const focusValidationField = useCallback((path: string) => {
    const section = sectionForValidationPath(path)
    if (section) {
      setOpenSections((sections) =>
        sections.includes(section) ? sections : [...sections, section],
      )
    }

    window.requestAnimationFrame(() => {
      window.requestAnimationFrame(() => {
        const field = controlForValidationPath(path)
        if (field) {
          field.scrollIntoView({ behavior: "smooth", block: "center" })
          field.focus({ preventScroll: true })
        }
      })
    })
  }, [])

  useEffect(() => {
    const markedElements = new Map<HTMLElement, string | null>()

    for (const entry of validationErrors) {
      const field = controlForValidationPath(entry.path)
      if (!field || markedElements.has(field)) continue

      markedElements.set(field, field.getAttribute("aria-invalid"))
      field.setAttribute("aria-invalid", "true")
      field.classList.add("border-destructive", "ring-1", "ring-destructive")
    }

    return () => {
      markedElements.forEach((previousAriaInvalid, field) => {
        if (previousAriaInvalid === null) field.removeAttribute("aria-invalid")
        else field.setAttribute("aria-invalid", previousAriaInvalid)
        field.classList.remove("border-destructive", "ring-1", "ring-destructive")
      })
    }
  }, [validationErrors])

  const showValidationErrors = useCallback((entries: ValidationErrorEntry[], message: string) => {
    form.clearErrors()
    for (const entry of entries) {
      if (entry.path === "__root__") continue
      form.setError(entry.path as FieldPath<FormValues>, {
        type: "server",
        message: entry.message,
      })
    }
    setValidationErrors(entries)
    setError(message)

    const firstPath = entries[0]?.path
    if (firstPath) focusValidationField(firstPath)
  }, [focusValidationField, form])

  const fileInputRef = useRef<HTMLInputElement>(null)
  const [stations, setStations] = useState<{ id: string; name: string }[]>([])
  const [stationLoading, setStationLoading] = useState(true)
  const [stationResolutionLoading, setStationResolutionLoading] = useState(false)
  const [stationResolutionMessage, setStationResolutionMessage] = useState<string | null>(null)
  const [stationResolutionError, setStationResolutionError] = useState<string | null>(null)

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
        form.reset(mergeFormValues(parsed))
      } catch (err) {
        setError("Nieprawidłowy plik JSON")
      }
    }
    reader.readAsText(file)
    event.target.value = ""
  }

  async function handleResolveStation() {
    const location = form.getValues("general.location_address")?.trim()
    if (!location || location.length < 2) {
      setStationResolutionMessage(null)
      setStationResolutionError("Wpisz miejscowość lub adres budynku.")
      return
    }

    setStationResolutionLoading(true)
    setStationResolutionMessage(null)
    setStationResolutionError(null)
    try {
      const resolution = await resolveClimateStation(location)
      form.setValue("climate_station_id", resolution.station.id, {
        shouldDirty: true,
        shouldValidate: true,
      })
      setStationResolutionMessage(
        `Dopasowano ${resolution.matched_location}. Najbliższa dostępna stacja: ${resolution.station.name} (${resolution.station.distance_km.toFixed(1)} km).`
      )
    } catch (err) {
      setStationResolutionError(
        err instanceof Error ? err.message : "Nie udało się dobrać stacji klimatycznej."
      )
    } finally {
      setStationResolutionLoading(false)
    }
  }

  function applyHeatingSourceDefaults(value: string) {
    const option = heatingSourceOptions.find((item) => item.value === value)
    if (!option) return
    form.setValue("systems.heating.fuel_or_carrier", option.carrier)
    form.setValue("systems.heating.generation_efficiency", option.generationEfficiency)
    if (option.sinkTemperature !== undefined) {
      form.setValue("systems.heating.sink_temperature", option.sinkTemperature)
    }
  }

  function applyBuildingTypeDefaults(value: string) {
    const profile = dhwUsageProfileByBuildingType[value as (typeof buildingTypeValues)[number]]
    if (!profile) return
    form.setValue("general.dhw_usage_profile", profile, {
      shouldDirty: true,
      shouldValidate: true,
    })
  }

  function applyCoolingSourceDefaults(value: string) {
    const option = coolingSourceOptions.find((item) => item.value === value)
    if (!option) return
    form.setValue("systems.cooling.fuel_or_carrier", option.carrier)
    form.setValue("systems.cooling.generation_efficiency", option.generationEfficiency)
  }

  function applyDhwSourceDefaults(value: string) {
    const option = dhwSourceOptions.find((item) => item.value === value)
    if (!option) return
    form.setValue("systems.dhw.fuel_or_carrier", option.carrier)
    form.setValue("systems.dhw.generation_efficiency", option.generationEfficiency)
  }

  function applyDhwDistributionDefaults(value: string) {
    const option = dhwDistributionOptions.find((item) => item.value === value)
    if (option) form.setValue("systems.dhw.distribution_efficiency", option.efficiency)
  }

  const zonesFieldArray = useFieldArray({ control: form.control, name: "thermal_zones" })
  const opaqueFieldArray = useFieldArray({ control: form.control, name: "opaque_building_elements" })
  const transparentFieldArray = useFieldArray({
    control: form.control,
    name: "transparent_building_elements",
  })
  const watchedZones = useWatch({ control: form.control, name: "thermal_zones" })
  const watchedOpaqueElements = useWatch({
    control: form.control,
    name: "opaque_building_elements",
  })
  const watchedTransparentElements = useWatch({
    control: form.control,
    name: "transparent_building_elements",
  })
  const zoneOptions = (watchedZones ?? [])
    .filter((zone) => zone.id.trim().length > 0)
    .filter(
      (zone, index, zones) =>
        zones.findIndex((candidate) => candidate.id === zone.id) === index
    )
    .map((zone) => ({
      value: zone.id,
      label: `${zone.id} — ${zone.name}`,
    }))

  useEffect(() => {
    const syncAreas = (
      elements: Array<{ height: number; width: number }> | undefined,
      fieldName: "opaque_building_elements" | "transparent_building_elements",
    ) => {
      elements?.forEach((element, index) => {
        const area = calculateElementArea(element.height, element.width)
        if (area === null) return
        const areaPath = `${fieldName}.${index}.area` as any
        const currentArea = Number(form.getValues(areaPath))
        if (!Number.isFinite(currentArea) || Math.abs(currentArea - area) > 1e-9) {
          form.setValue(areaPath, area, { shouldDirty: true, shouldValidate: true })
        }
      })
    }

    syncAreas(watchedOpaqueElements, "opaque_building_elements")
    syncAreas(watchedTransparentElements, "transparent_building_elements")
  }, [form, watchedOpaqueElements, watchedTransparentElements])

  const onSubmit = useCallback(async (values: FormValues) => {
    form.clearErrors()
    setError(null)
    setValidationErrors([])
    setLoading(true)
    try {
      const project = createProjectPayload(values)
      setProject(project)
      const result = await calculate(project)
      setResult(result)
      addToHistory()
    } catch (err) {
      if (err instanceof CalculationRequestError && err.validationIssues.length > 0) {
        const entries = normalizeServerValidationErrors(err.validationIssues, values)
        showValidationErrors(
          entries,
          "Backend odrzucił część danych. Popraw pola oznaczone na czerwono; opis przy każdym polu wyjaśnia wymaganie.",
        )
        return
      }
      setError(err instanceof Error ? err.message : "Unknown error")
    } finally {
      setLoading(false)
    }
  }, [addToHistory, form, setProject, setResult, showValidationErrors])

  const onInvalid = useCallback((errors: FieldErrors<FormValues>) => {
    const entries = collectValidationErrors(errors)
    showValidationErrors(entries, "Nie można uruchomić obliczeń, dopóki formularz zawiera błędy.")
  }, [showValidationErrors])

  useEffect(() => {
    if (
      isNewProject ||
      !historyId ||
      !historyItem ||
      !currentProject ||
      currentResult ||
      autoCalculationAttemptedRef.current === historyId
    ) {
      return
    }

    autoCalculationAttemptedRef.current = historyId
    const timer = window.setTimeout(() => {
      void form.handleSubmit(onSubmit, onInvalid)()
    }, 0)

    return () => window.clearTimeout(timer)
  }, [currentProject, currentResult, form, historyId, historyItem, isNewProject, onInvalid, onSubmit])

  const inputClass = "max-w-sm"

  return (
    <main className="container mx-auto py-8 px-4">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-6">
        <h1 className="text-3xl font-bold">Nowa analiza energetyczna</h1>
        <div className="flex flex-wrap items-center justify-end gap-3">
          <span className="text-xs text-muted-foreground" aria-live="polite">
            {autosaveState === "saving"
              ? "Autozapis…"
              : autosaveState === "saved"
                ? "Autozapis: zapisano"
                : "Autozapis gotowy"}
          </span>
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
      </div>
      <form noValidate onSubmit={form.handleSubmit(onSubmit, onInvalid)}>
        <Accordion
          type="multiple"
          value={openSections}
          onValueChange={setOpenSections}
          className="space-y-4"
        >
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
                <FormSelect
                  name="general.building_type"
                  control={form.control}
                  label="Typ budynku"
                  tooltip="Kategoria budynku używana do profilów wewnętrznych i OZE."
                  placeholder="Wybierz typ budynku"
                  className={inputClass}
                  options={[
                    { value: "residential", label: "Mieszkalny" },
                    { value: "office", label: "Biurowy" },
                    { value: "school", label: "Szkoła" },
                    { value: "retail", label: "Handlowo-usługowy" },
                    { value: "healthcare", label: "Ochrona zdrowia" },
                    { value: "other", label: "Inny" },
                  ]}
                  onChange={applyBuildingTypeDefaults}
                />
                <FormSelect
                  name="general.dhw_usage_profile"
                  control={form.control}
                  label="Profil standardowego użytkowania CWU"
                  tooltip="Profil VWi i współczynnik kR z tabeli 27 metodologii. Na jego podstawie, wraz z powierzchnią Af, system wyznacza roczne zapotrzebowanie użytkowe QW,nd."
                  placeholder="Wybierz profil CWU"
                  className={inputClass}
                  options={[
                    { value: "residential_single_family", label: "Mieszkalny jednorodzinny" },
                    { value: "residential_multi_family_lump_sum", label: "Mieszkalny wielorodzinny – rozliczenie ryczałtowe" },
                    { value: "residential_multi_family_individual_metering", label: "Mieszkalny wielorodzinny – indywidualne opomiarowanie" },
                    { value: "office", label: "Biurowy" },
                    { value: "education", label: "Oświata / szkolnictwo wyższe / nauka" },
                    { value: "healthcare", label: "Ochrona zdrowia" },
                    { value: "retail_services", label: "Handel i usługi" },
                    { value: "collective_residential", label: "Zamieszkanie zbiorowe" },
                    { value: "warehouse", label: "Magazyn" },
                  ]}
                />
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
                <FormField
                  label="LENI oświetlenia (kWh/m²·r)"
                  tooltip="Wskaźnik LENI wg PN-EN 15193 dla wbudowanej instalacji oświetlenia (wzór (35) metodologii). Liczone tylko dla budynków niemieszkalnych; zostaw puste, aby pominąć oświetlenie."
                >
                  <Input id="lighting_indicator_leni" type="number" step="0.1" placeholder="np. 15" {...form.register("general.lighting_indicator_leni")} className={inputClass} />
                </FormField>
                <FormField
                  label="Powierzchnia oświetlana (m²)"
                  tooltip="A_L – powierzchnia pomieszczeń z wbudowanym oświetleniem. Domyślnie równa powierzchni ogrzewanej."
                >
                  <Input id="lighting_area_m2" type="number" step="0.1" placeholder="np. 150" {...form.register("general.lighting_area_m2")} className={inputClass} />
                </FormField>
                <FormField
                  label="Lokalizacja budynku"
                  tooltip="Wpisz miejscowość, kod pocztowy lub adres. Po kliknięciu przycisku aplikacja dobierze najbliższą dostępną stację TMY."
                  className="md:col-span-2"
                >
                  <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
                    <Input
                      id="location_address"
                      placeholder="np. ul. Marszałkowska 1, Warszawa"
                      {...form.register("general.location_address")}
                      className="sm:max-w-sm"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={handleResolveStation}
                      disabled={stationResolutionLoading}
                    >
                      {stationResolutionLoading ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                      ) : (
                        <MapPin className="mr-2 h-4 w-4" />
                      )}
                      {stationResolutionLoading ? "Dobieranie…" : "Dobierz stację"}
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Wyszukiwanie działa dla lokalizacji w Polsce. Zapytanie jest wysyłane do geokodera
                    Open-Meteo dopiero po kliknięciu przycisku.
                  </p>
                  {stationResolutionMessage && (
                    <p className="text-sm text-emerald-700">{stationResolutionMessage}</p>
                  )}
                  {stationResolutionError && (
                    <p className="text-sm text-destructive">{stationResolutionError}</p>
                  )}
                </FormField>
                <FormField label="Stacja klimatyczna" tooltip="Predefiniowany zbiór danych TMY (Typical Meteorological Year) używany do symulacji godzinowej. Wybierz najbliższą lokalizację.">
                  <Controller
                    name="climate_station_id"
                    control={form.control}
                    render={({ field, fieldState }) => (
                      <Select
                        name={field.name}
                        value={field.value}
                        onValueChange={field.onChange}
                        disabled={stationLoading}
                      >
                        <SelectTrigger
                          className={fieldState.invalid ? `${inputClass} border-destructive ring-1 ring-destructive` : inputClass}
                          data-field-path={field.name}
                          aria-invalid={fieldState.invalid}
                        >
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
                      <FormField label="Typ strefy" tooltip="Rodzaj strefy: ogrzewana, chłodzona lub nieogrzewana.">
                        <Controller
                          name={`thermal_zones.${index}.zone_type` as any}
                          control={form.control}
                          render={({ field, fieldState }) => (
                            <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger
                                data-field-path={field.name}
                                aria-invalid={fieldState.invalid}
                                className={fieldState.invalid ? "border-destructive ring-1 ring-destructive" : undefined}
                              >
                                <SelectValue placeholder="Wybierz typ" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="heated">Ogrzewana</SelectItem>
                                <SelectItem value="cooled">Chłodzona</SelectItem>
                                <SelectItem value="heated_and_cooled">Ogrzewana i chłodzona</SelectItem>
                                <SelectItem value="unheated">Nieogrzewana</SelectItem>
                                <SelectItem value="semi_heated">Częściowo ogrzewana</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        />
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
                      <FormField label="Temp. chłodzenia (°C)" tooltip="Górna temperatura akceptowalna w sezonie chłodniczym. Uwaga: liczy się wyłącznie dla typów stref „Chłodzona” i „Ogrzewana i chłodzona” — dla strefy „Ogrzewana” budynek będzie się przegrzewał bez chłodzenia (zgodnie z § 5.4 metodologii Q_C,nd wyznacza się tylko dla stref chłodzonych).">
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
                każdej przegrody podaj wysokość, szerokość i współczynnik
                przenikania ciepła U. Powierzchnia zostanie obliczona jako
                wysokość × szerokość.
              </p>
              <div className="space-y-4">
                {opaqueFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <div className="md:col-span-4 flex items-center justify-between border-b pb-3">
                        <span className="text-sm font-semibold text-slate-700">
                          Przegroda {index + 1}
                        </span>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => opaqueFieldArray.remove(index)}
                          aria-label={`Usuń przegrodę nieprzezroczystą ${index + 1}`}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Usuń przegrodę
                        </Button>
                      </div>
                      <FormField label="ID" tooltip="Unikalny skrót, np. wall_n, roof. Używany w raportach.">
                        <Input placeholder="np. wall_n" {...form.register(`opaque_building_elements.${index}.id`)} />
                      </FormField>
                      <FormField label="Nazwa" tooltip="Czytelna nazwa, np. „Ściana północna”.">
                        <Input placeholder="np. Ściana północna" {...form.register(`opaque_building_elements.${index}.name`)} />
                      </FormField>
                      <FormSelect
                        name={`opaque_building_elements.${index}.zone_id` as any}
                        control={form.control}
                        label="ID strefy"
                        tooltip="Wybierz wcześniej zdefiniowaną strefę termiczną. Lista pokazuje ID oraz nazwę strefy."
                        placeholder="Wybierz strefę"
                        options={zoneOptions}
                      />
                      <FormField label="Typ przegrody" tooltip="Rodzaj przegrody – ściana, dach, strop, podłoga na gruncie lub ściana między lokalami.">
                        <Controller
                          name={`opaque_building_elements.${index}.element_type` as any}
                          control={form.control}
                          render={({ field, fieldState }) => (
                            <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger
                                data-field-path={field.name}
                                aria-invalid={fieldState.invalid}
                                className={fieldState.invalid ? "border-destructive ring-1 ring-destructive" : undefined}
                              >
                                <SelectValue placeholder="Wybierz typ" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="external_wall">Ściana zewnętrzna</SelectItem>
                                <SelectItem value="roof">Dach / stropodach</SelectItem>
                                <SelectItem value="ground_floor">Podłoga na gruncie</SelectItem>
                                <SelectItem value="floor_over_unheated">Strop nad piwnicą / poddaszem</SelectItem>
                                <SelectItem value="internal_wall">Ściana wewnętrzna</SelectItem>
                                <SelectItem value="basement_wall">Ściana piwnicy</SelectItem>
                                <SelectItem value="party_wall">Ściana między lokalami</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        />
                      </FormField>
                      <FormField label="Azymut (°)" tooltip="Kierunek ściany: 0 = północ, 90 = wschód, 180 = południe, 270 = zachód. Dla poziomych (dach, podłoga) wpisz 0.">
                        <Input type="number" step="0.1" placeholder="0-360" {...form.register(`opaque_building_elements.${index}.orientation_azimuth`)} />
                      </FormField>
                      <FormField label="Nachylenie (°)" tooltip="Kąt do płaszczyzny poziomej. Ściana = 90°, dach płaski = 0°, podłoga na gruncie = 180°.">
                        <Input type="number" step="0.1" placeholder="0-180" {...form.register(`opaque_building_elements.${index}.inclination`)} />
                      </FormField>
                      <FormField label="Wysokość (m)" tooltip="Wysokość przegrody. Dla dachu lub podłogi wpisz pierwszy wymiar rzutu.">
                        <Input type="number" min="0.01" step="0.01" placeholder="np. 4" {...form.register(`opaque_building_elements.${index}.height`)} />
                      </FormField>
                      <FormField label="Szerokość (m)" tooltip="Szerokość przegrody. Dla dachu lub podłogi wpisz drugi wymiar rzutu.">
                        <Input type="number" min="0.01" step="0.01" placeholder="np. 10" {...form.register(`opaque_building_elements.${index}.width`)} />
                      </FormField>
                      <FormField label="Powierzchnia (m²)" tooltip="Wyliczana automatycznie jako wysokość × szerokość.">
                        <Input
                          type="number"
                          step="0.01"
                          readOnly
                          aria-readonly="true"
                          className="bg-slate-50"
                          {...form.register(`opaque_building_elements.${index}.area`)}
                        />
                      </FormField>
                      <FormField label="U (W/m²K)" tooltip="Współczynnik przenikania ciepła. Niższa wartość = mniejsze straty ciepła.">
                        <Input type="number" step="0.01" placeholder="np. 0.25" {...form.register(`opaque_building_elements.${index}.u_value`)} />
                      </FormField>
                      <FormField label="Absorpcja słońca (α)" tooltip="Współczynnik absorpcji promieniowania słonecznego powierzchni (0 = odbija wszystko, 1 = pochłania wszystko). Dla farb jasnych ~0.4, ciemnych ~0.8. Silnik liczy zysk do wewnątrz fizycznie: A·α·U·Rse·I.">
                        <Input type="number" step="0.01" placeholder="0-1" {...form.register(`opaque_building_elements.${index}.solar_absorptance`)} />
                      </FormField>
                      <FormField label="Przestrzeń sąsiednia" tooltip="Co znajduje się po drugiej stronie przegrody. Ma wpływ na temperaturę i straty ciepła.">
                        <Controller
                          name={`opaque_building_elements.${index}.adjacent_space_type` as any}
                          control={form.control}
                          render={({ field, fieldState }) => (
                            <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger
                                data-field-path={field.name}
                                aria-invalid={fieldState.invalid}
                                className={fieldState.invalid ? "border-destructive ring-1 ring-destructive" : undefined}
                              >
                                <SelectValue placeholder="Wybierz przestrzeń" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="outdoor">Powietrze zewnętrzne</SelectItem>
                                <SelectItem value="ground">Grunt</SelectItem>
                                <SelectItem value="unheated_zone">Nieogrzewane pomieszczenie</SelectItem>
                                <SelectItem value="heated_zone">Inna ogrzewana strefa</SelectItem>
                                <SelectItem value="constant_temperature">Przestrzeń o stałej temperaturze</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        />
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
                Okna, drzwi przeszklone, świetliki. Podaj wysokość i szerokość,
                a powierzchnia zostanie obliczona automatycznie. Współczynnik g
                i udział ramy redukują zyski solarne.
              </p>
              <div className="space-y-4">
                {transparentFieldArray.fields.map((field, index) => (
                  <Card key={field.id}>
                    <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-4">
                      <div className="md:col-span-4 flex items-center justify-between border-b pb-3">
                        <span className="text-sm font-semibold text-slate-700">
                          Przegroda transparentna {index + 1}
                        </span>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => transparentFieldArray.remove(index)}
                          aria-label={`Usuń przegrodę transparentną ${index + 1}`}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          Usuń przegrodę
                        </Button>
                      </div>
                      <FormField label="ID" tooltip="Unikalny skrót, np. win_s, drzwi_e.">
                        <Input placeholder="np. win_s" {...form.register(`transparent_building_elements.${index}.id`)} />
                      </FormField>
                      <FormField label="Nazwa" tooltip="Czytelna nazwa, np. „Okno południowe”.">
                        <Input placeholder="np. Okno południowe" {...form.register(`transparent_building_elements.${index}.name`)} />
                      </FormField>
                      <FormSelect
                        name={`transparent_building_elements.${index}.zone_id` as any}
                        control={form.control}
                        label="ID strefy"
                        tooltip="Wybierz wcześniej zdefiniowaną strefę termiczną. Lista pokazuje ID oraz nazwę strefy."
                        placeholder="Wybierz strefę"
                        options={zoneOptions}
                      />
                      <FormField label="Typ transparentu" tooltip="Rodzaj elementu przeszklonego: okno, drzwi przeszklone, świetlik.">
                        <Controller
                          name={`transparent_building_elements.${index}.element_type` as any}
                          control={form.control}
                          render={({ field, fieldState }) => (
                            <Select name={field.name} value={field.value} onValueChange={field.onChange}>
                              <SelectTrigger
                                data-field-path={field.name}
                                aria-invalid={fieldState.invalid}
                                className={fieldState.invalid ? "border-destructive ring-1 ring-destructive" : undefined}
                              >
                                <SelectValue placeholder="Wybierz typ" />
                              </SelectTrigger>
                              <SelectContent>
                                <SelectItem value="window">Okno</SelectItem>
                                <SelectItem value="glass_door">Drzwi przeszklone</SelectItem>
                                <SelectItem value="skylight">Świetlik</SelectItem>
                              </SelectContent>
                            </Select>
                          )}
                        />
                      </FormField>
                      <FormField label="Azymut (°)" tooltip="Kierunek okna: 0 = północ, 90 = wschód, 180 = południe, 270 = zachód.">
                        <Input type="number" step="0.1" placeholder="0-360" {...form.register(`transparent_building_elements.${index}.orientation_azimuth`)} />
                      </FormField>
                      <FormField label="Nachylenie (°)" tooltip="Kąt do poziomu. Standardowe okno = 90°, świetlik = 0°.">
                        <Input type="number" step="0.1" placeholder="0-180" {...form.register(`transparent_building_elements.${index}.inclination`)} />
                      </FormField>
                      <FormField label="Wysokość (m)" tooltip="Wysokość całkowita okna, drzwi lub świetlika.">
                        <Input type="number" min="0.01" step="0.01" placeholder="np. 2" {...form.register(`transparent_building_elements.${index}.height`)} />
                      </FormField>
                      <FormField label="Szerokość (m)" tooltip="Szerokość całkowita okna, drzwi lub świetlika.">
                        <Input type="number" min="0.01" step="0.01" placeholder="np. 5" {...form.register(`transparent_building_elements.${index}.width`)} />
                      </FormField>
                      <FormField label="Powierzchnia (m²)" tooltip="Wyliczana automatycznie jako wysokość × szerokość.">
                        <Input
                          type="number"
                          step="0.01"
                          readOnly
                          aria-readonly="true"
                          className="bg-slate-50"
                          {...form.register(`transparent_building_elements.${index}.area`)}
                        />
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

          <AccordionItem value="systems">
            <AccordionTrigger>Źródła energii i instalacje techniczne</AccordionTrigger>
            <AccordionContent>
              <p className="text-sm text-slate-600 mb-4">
                Wybierz źródło dla każdego systemu. Wartości sprawności są
                domyślnymi wartościami tabel metodologii; jeżeli masz dane
                producenta lub dokumentację instalacji, zastąp nimi wartości
                domyślne.
              </p>

              <div className="space-y-6">
                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Ogrzewanie</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormSelect
                      name="systems.heating.system_type"
                      control={form.control}
                      label="Źródło ciepła"
                      tooltip="Rodzaj źródła z tabeli ηH,g. Wybór uzupełnia nośnik i wartość domyślną sprawności wytwarzania."
                      placeholder="Wybierz źródło ciepła"
                      className={inputClass}
                      options={heatingSourceOptions.map(({ value, label }) => ({ value, label }))}
                      onChange={applyHeatingSourceDefaults}
                    />
                    <FormSelect
                      name="systems.heating.fuel_or_carrier"
                      control={form.control}
                      label="Nośnik energii"
                      tooltip="Nośnik energii używany przez źródło; wpływa na energię pierwotną."
                      className={inputClass}
                      options={energyCarrierOptions}
                    />
                    <div className="rounded-md border border-dashed bg-slate-50 p-3 text-sm text-slate-600 md:col-span-2">
                      Moc źródła ciepła zostanie dobrana automatycznie po
                      obliczeniu szczytowych strat przez przenikanie i wentylację.
                      Nie wpisujesz jej ręcznie.
                    </div>
                    <FormField label="ηH,g / COP" tooltip="Średnia sezonowa sprawność wytwarzania ciepła albo współczynnik wydajności pompy ciepła.">
                      <Input type="number" step="0.01" {...form.register("systems.heating.generation_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηH,d – przesył" tooltip="Średnia sezonowa sprawność przesyłu ciepła ze źródła do przestrzeni ogrzewanej.">
                      <Input type="number" step="0.01" {...form.register("systems.heating.distribution_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηH,s – akumulacja" tooltip="Średnia sezonowa sprawność akumulacji ciepła w elementach pojemnościowych systemu ogrzewania.">
                      <Input type="number" step="0.01" {...form.register("systems.heating.storage_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηH,e – regulacja i wykorzystanie" tooltip="Średnia sezonowa sprawność regulacji i wykorzystania ciepła w przestrzeni ogrzewanej.">
                      <Input type="number" step="0.01" {...form.register("systems.heating.control_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="Temperatura zasilania (°C)" tooltip="Temperatura po stronie odbioru używana przy charakterystyce pompy ciepła.">
                      <Input type="number" step="0.1" {...form.register("systems.heating.sink_temperature")} className={inputClass} />
                    </FormField>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Ciepła woda użytkowa (CWU)</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormSelect
                      name="systems.dhw.system_type"
                      control={form.control}
                      label="Źródło CWU"
                      tooltip="Rodzaj źródła z tabeli ηW,g. Wybór uzupełnia nośnik i wartość domyślną sprawności wytwarzania."
                      placeholder="Wybierz źródło CWU"
                      className={inputClass}
                      options={dhwSourceOptions.map(({ value, label }) => ({ value, label }))}
                      onChange={applyDhwSourceDefaults}
                    />
                    <FormSelect
                      name="systems.dhw.fuel_or_carrier"
                      control={form.control}
                      label="Nośnik energii CWU"
                      tooltip="Nośnik energii przypisany do źródła CWU."
                      className={inputClass}
                      options={energyCarrierOptions}
                    />
                    <div className="rounded-md border border-dashed bg-slate-50 p-3 text-sm text-slate-600 md:col-span-2">
                      Roczne zapotrzebowanie użytkowe CWU (QW,nd) jest wyznaczane
                      automatycznie z powierzchni ogrzewanej Af oraz profilu
                      standardowego użytkowania wybranego w informacjach ogólnych,
                      zgodnie z tabelą 27 metodologii. Metoda przyjmuje temperaturę
                      wody ciepłej 55°C, wody zimnej 10°C i 365 dni w roku.
                    </div>
                    <FormSelect
                      name="systems.dhw.distribution_type"
                      control={form.control}
                      label="Typ przesyłu CWU"
                      tooltip="Wariant instalacji odpowiadający tabeli ηW,d; wybór ustawia domyślną sprawność przesyłu."
                      className={inputClass}
                      options={dhwDistributionOptions.map(({ value, label }) => ({ value, label }))}
                      onChange={applyDhwDistributionDefaults}
                    />
                    <FormField label="ηW,g / COP" tooltip="Średnia roczna sprawność wytwarzania ciepła albo współczynnik wydajności pompy ciepła.">
                      <Input type="number" step="0.01" {...form.register("systems.dhw.generation_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηW,d – przesył" tooltip="Średnia roczna sprawność przesyłu ciepła ze źródła do zaworów czerpalnych.">
                      <Input type="number" step="0.01" {...form.register("systems.dhw.distribution_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηW,s – akumulacja" tooltip="Średnia roczna sprawność akumulacji ciepła w zasobniku CWU.">
                      <Input type="number" step="0.01" {...form.register("systems.dhw.storage_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηW,e – wykorzystanie" tooltip="Średnia roczna sprawność wykorzystania ciepła; metodologia przyjmuje 1,0.">
                      <Input type="number" step="0.01" {...form.register("systems.dhw.utilization_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField
                      label="Zasobnik – pojemność (dm³)"
                      tooltip="V_S zasobnika CWU. Po podaniu pojemności straty postoju ΔQW,s liczone są dokładnie z tabeli 13 i wzoru (30) metodologii (pole ηW,s jest wtedy pomijane)."
                    >
                      <Input type="number" step="1" placeholder="np. 200" {...form.register("systems.dhw.storage_volume_dm3")} className={inputClass} />
                    </FormField>
                    <>
                      <FormSelect
                        name="systems.dhw.storage_location"
                        control={form.control}
                        label="Zasobnik – lokalizacja"
                        tooltip="Przestrzeń nieogrzewana (np. piwnica, garaż) lub ogrzewana – wpływa na straty jednostkowe q_S z tabeli 13."
                        className={inputClass}
                        options={[
                          { value: "unheated", label: "Przestrzeń nieogrzewana" },
                          { value: "heated", label: "Przestrzeń ogrzewana" },
                        ]}
                      />
                    </>
                    <FormField
                      label="Zasobnik – izolacja (mm)"
                      tooltip="Grubość izolacji termicznej zasobnika pośrednio podgrzewanego: 100, 50 lub 20 mm (kolumny tabeli 13)."
                    >
                      <Input type="number" step="10" placeholder="np. 50" {...form.register("systems.dhw.storage_insulation_mm")} className={inputClass} />
                    </FormField>
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-lg">Chłodzenie</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <FormSelect
                      name="systems.cooling.system_type"
                      control={form.control}
                      label="Źródło chłodu"
                      tooltip="Rodzaj systemu z tabeli SEERref. Wybór uzupełnia nośnik i domyślny SEER."
                      placeholder="Wybierz źródło chłodu"
                      className={inputClass}
                      options={[
                        { value: "none", label: "Brak systemu chłodzenia" },
                        ...coolingSourceOptions.map(({ value, label }) => ({ value, label })),
                      ]}
                      onChange={applyCoolingSourceDefaults}
                    />
                    <FormSelect
                      name="systems.cooling.fuel_or_carrier"
                      control={form.control}
                      label="Nośnik energii chłodzenia"
                      tooltip="Nośnik energii przypisany do źródła chłodu."
                      className={inputClass}
                      options={energyCarrierOptions}
                    />
                    <div className="rounded-md border border-dashed bg-slate-50 p-3 text-sm text-slate-600 md:col-span-2">
                      Roczne zapotrzebowanie użytkowe chłodzenia (QC,nd) jest
                      wyznaczane z godzinowego bilansu zysków i strat stref
                      chłodzonych. Moc nominalna źródła nie jest wejściem do
                      obliczeń rocznych.
                    </div>
                    <FormField label="SEER" tooltip="Średni sezonowy współczynnik efektywności energetycznej wytwarzania chłodu.">
                      <Input type="number" step="0.01" {...form.register("systems.cooling.generation_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηC,d – przesył" tooltip="Średnia sezonowa sprawność przesyłu chłodu ze źródła do przestrzeni chłodzonej.">
                      <Input type="number" step="0.01" {...form.register("systems.cooling.distribution_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηC,s – akumulacja" tooltip="Średnia sezonowa sprawność akumulacji chłodu w elementach pojemnościowych.">
                      <Input type="number" step="0.01" {...form.register("systems.cooling.storage_efficiency")} className={inputClass} />
                    </FormField>
                    <FormField label="ηC,e – regulacja i wykorzystanie" tooltip="Średnia sezonowa sprawność regulacji i wykorzystania chłodu w przestrzeni chłodzonej.">
                      <Input type="number" step="0.01" {...form.register("systems.cooling.control_efficiency")} className={inputClass} />
                    </FormField>
                  </CardContent>
                </Card>
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
                <FormSelect
                  name="ventilation.ventilation_type"
                  control={form.control}
                  label="Typ wentylacji"
                  tooltip="Rodzaj instalacji wentylacyjnej."
                  placeholder="Wybierz typ wentylacji"
                  className={inputClass}
                  options={[
                    { value: "natural", label: "Grawitacyjna" },
                    { value: "exhaust", label: "Wywiewna" },
                    { value: "mechanical", label: "Mechaniczna" },
                    { value: "mechanical_with_recovery", label: "Mechaniczna z rekuperacją" },
                    { value: "hybrid", label: "Hybrydowa" },
                    { value: "none", label: "Brak wentylacji" },
                  ]}
                />
                <FormField label="Strumień powietrza (m³/h)" tooltip="Budynkowy strumień powietrza wentylacyjnego. Wpisz 0, aby pobrać wartość normatywną z tabel 24/25 metodologii (V0 wg profilu użytkowania budynku).">
                  <Input type="number" step="0.1" placeholder="np. 120" {...form.register("ventilation.airflow_rate")} className={inputClass} />
                </FormField>
                <FormField label="Sprawność odzysku" tooltip="Sprawność rekuperatora (0 = brak, 0.8 = wysoka). Dla wentylacji grawitacyjnej zostaw 0.">
                  <Input type="number" step="0.01" placeholder="0-1" {...form.register("ventilation.heat_recovery_efficiency")} className={inputClass} />
                </FormField>
                <FormField label="Współczynnik infiltracji (1/h)" tooltip="Liczba wymian powietrza na godzinę w wyniku nieszczelności. Dla budynków szczelnych 0.1-0.3, dla starszych 0.5-1.0.">
                  <Input type="number" step="0.01" placeholder="np. 0.5" {...form.register("ventilation.infiltration_rate")} className={inputClass} />
                </FormField>
                <FormField label="Udział użytkowania β" tooltip="β – udział czasu użytkowania budynku (§ 5.5.2 metodologii). Redukuje normatywny strumień wentylacji i czas pracy wentylatorów poza okresem użytkowania (tabele 20 i 22). Dla mieszkalnych = 1 (praca ciągła), dla biur typowo ~0.3.">
                  <Input type="number" step="0.01" placeholder="np. 0.3" {...form.register("ventilation.usage_share_beta")} className={inputClass} />
                </FormField>
              </div>
            </AccordionContent>
          </AccordionItem>
        </Accordion>

        {error && (
          <Alert variant="destructive" className="mt-6">
            <AlertTitle>
              {validationErrors.length > 0 ? "Uzupełnij dane" : "Błąd obliczeń"}
            </AlertTitle>
            <AlertDescription>
              <p>{error}</p>
              {validationErrors.length > 0 && (
                <ul className="mt-2 list-disc space-y-1 pl-5">
                  {validationErrors.map((entry) => (
                    <li key={`${entry.path}-${entry.message}`}>
                      <button
                        type="button"
                        className="text-left underline underline-offset-2"
                        onClick={() => {
                          const field = document.querySelector(`[name="${entry.path}"]`)
                          if (field instanceof HTMLElement) {
                            field.scrollIntoView({ behavior: "smooth", block: "center" })
                            field.focus({ preventScroll: true })
                          }
                        }}
                      >
                        {formatValidationPath(entry.path)}: {formatValidationMessage(entry.message)}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </AlertDescription>
          </Alert>
        )}

        <div className="mt-8 flex gap-4">
          <Button type="submit" size="lg" disabled={loading}>
            {loading ? "Obliczanie..." : "Oblicz charakterystykę"}
          </Button>
        </div>
      </form>

      {currentResult && (
        <div className="mt-12 border-t pt-10">
          <CalculationResults result={currentResult} project={currentProject} />
        </div>
      )}
    </main>
  )
}

export default function BuildingFormPage() {
  return (
    <Suspense fallback={<main className="container mx-auto px-4 py-8">Ładowanie formularza…</main>}>
      <BuildingFormContent />
    </Suspense>
  )
}
